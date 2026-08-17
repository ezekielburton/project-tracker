from flask import Blueprint, render_template, jsonify, request, abort
from flask_login import login_required
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import nullslast
from app import db
from app.models import Project, ProjectSecondaryCS, ProjectDesigner, ActivityLog, User, Deliverable, DecisionFlag, DeliverableAssignment
from app.utils import get_actor
from app.dashboard_logic import get_next_action_owner, get_project_rag, nearest_deadline, compute_clashes, guidance_for_viewer

# NOTE: registered blueprint name is 'projects' (not 'dashboard') — every
# url_for() call for this blueprint's routes uses that, e.g.
# url_for('projects.api_summary'). URL prefix is still /dashboard.
dashboard_bp = Blueprint('projects', __name__, url_prefix='/dashboard')

# Maps the ?view= query param (set by auth.login()'s role-based redirect) to
# the card key that should auto-expand on first paint. This is the only
# place that mapping lives — dashboard.js reads initial_expanded_card from
# the page rather than re-deriving it from the URL itself.
#
# 'due'/'at-risk' REMOVED (15 Jul 2026, same day as the rest of this
# section's redesign) — 'due' and 'at_risk' are no longer tab keys at all
# (see the big comment above CARD_ORDER below), so mapping either of them
# here would resolve initial_expanded_card to a card that doesn't exist in
# card_order, leaving NOTHING marked active on page load. Neither was ever
# actually reachable in production (no login redirect or link in the app
# sets ?view=due or ?view=at-risk — confirmed via a repo-wide search before
# removing), so this is a preemptive fix for a latent footgun, not a real
# regression.
#
# 'my-week' -> 'summary' REMOVED too (15 Jul 2026, later still, same day
# as the top-of-page redesign — see the big comment above CARD_ORDER) —
# 'summary' is no longer a card_order key at all now that My Day/My Week
# lives in its own always-visible toggle box instead of a tab, so this
# entry would hit the exact same "resolves to a card that doesn't exist"
# footgun the 'due'/'at-risk' removal above was written to avoid. Like
# those two, this was already unreachable in production (auth.py's
# ?view=my-week login redirect is commented out — see auth.py's login()).
VIEW_TO_CARD = {
    'decisions': 'decisions',
}

# ── Dashboard layout, redesigned 15 Jul 2026 ────────────────────────────
# Per Ezekiel: "Have the my day/my week div be the interactive area where
# the information populates. Where my day/my week is lets have the tabs
# for each card that are clickable." Previously Summary ("My Day / My
# Week") was a separate, permanently-open, non-interactive block ABOVE a
# 5-per-row tile grid + a single shared expand area below it (see
# dashboard.html's git history around 12 Jul 2026 for that design). Then
# there was exactly one interactive content area — the same box that used
# to be Summary-only — driven by a tab strip directly above it, one tab
# per card INCLUDING Summary itself (first tab, active by default).
#
# SUPERSEDED again, later the same day — see the "tab strip to top of
# page" section in CLAUDE.md. Per Ezekiel: "Bring the tabs up to the top
# of the page... Bring my day/my week to the right side... Remove myday/
# my week button since it will be redundant." My Day/My Week (and Overdue/
# At Risk, moved out of the tab strip earlier the same day) are now BOTH
# permanent, collapsible toggle boxes sitting above the tab strip — see
# .dash-toggle-row in dashboard.html — so 'summary' is REMOVED from
# CARD_ORDER entirely below, the same "don't render the same data twice,
# once as a tab and once elsewhere" reasoning 'due'/'at_risk' were removed
# for. See _dashboard_macros.html's dash_card() docstring for the
# remaining tab/body mode mechanic and dashboard.html for the markup.
#
# _STAT_TILES (Your Active / Pending Approval / Average Project Time —
# 'stat_total' REMOVED same day, per Ezekiel: "Remove total active
# projects also" — see _compute_total_active_projects()'s docstring,
# below, for where that card's old compute function went) — added 12-13
# Jul 2026 as a separate non-tab static tile row above the tab strip (no
# expandable body content). MOVED DOWN into ordinary tab+body cards 15 Jul
# 2026, same day as the CS/Designer toggle rework, per Ezekiel: "have the
# rest of the cards ... move down also. And when they click them it shows
# the relevant information in the information area." Now just a plain
# suffix appended to the END of every role's CARD_ORDER list below (per
# Ezekiel: tab order should have these "last, after all the other
# cards") — each now has a real `dash_card()` body:
#   stat_active/stat_pending — a plain project list (see
#     dash_stat_project_row() in _dashboard_macros.html and
#     _compute_your_active_projects()/_compute_pending_approval_projects()
#     below) of exactly the projects counted in that tile's number.
#   stat_avg_time — admin/management ONLY (per Ezekiel: "keep it
#     management only for clickable"): the full company-wide project +
#     deliverable hours breakdown, same data/markup as the standalone
#     /time-tracking page (build_time_tracking_rows(), imported from
#     app.routes.time_tracking — see stat_avg_time.html). Every other role
#     still sees the tile's own number (their personal scoped average,
#     unchanged), just can't click into it — same `muted` mechanic Clashing
#     Projects uses at zero clashes, not the old <a>-vs-<div> link swap.
#     The standalone /time-tracking route/page itself is UNCHANGED and
#     still reachable directly — this card no longer links out to it
#     (per Ezekiel: "keep it but unlink it, we can work on it later").
_STAT_TILES = ['stat_active', 'stat_pending', 'stat_avg_time']

# Secondary Metrics row — originally built for the CS-only redesigned
# dashboard (16 Jul 2026 — see the big comment above _serialize_owners_list()
# further down). NOT the same list as CARD_ORDER['cs'] below (that one still
# exists, unused while layout_role == 'cs', only as a harmless leftover for
# the old template's own CARD_ORDER.get() fallback logic) — per Ezekiel:
# "Secondary metrics at the bottom holds active projects, pending approval,
# overdue, clashes, which are all clickable like now and keep the same way
# the expanded data is shown." 'due' and 'clashes' UN-ORPHANED here —
# due.html had been orphaned since 15 Jul 2026 (Overdue moved into the
# toggle box on the old layout) and is reused as-is for its "Overdue"
# secondary-metric tile; clashes.html was never orphaned, reused as-is too
# (its by-deliverable/by-project body is unchanged — see clashes.html for
# the one small title tweak, gated on dash_cs_layout). Reuses the exact
# same dash_card() tab+body mechanic every card in CARD_ORDER already uses
# (mode='tab'/'body', see _dashboard_macros.html) — "keep the same way the
# expanded data is shown" — just a shorter list and a different spot on the
# page (see dashboard_cs.html).
#
# WIDENED to the leadership dashboard too (16 Jul 2026, same day) — per
# Ezekiel, sharing a screenshot of these exact 5 tiles: "add this to the
# management view also, at the bottom." Same list, same compute functions
# (all already role/scope-aware via scope_user — see each function's own
# docstring), just a second render_template() call in index()'s
# 'management'/'admin' branch passes the same kwargs dashboard_cs.html's
# branch already did. No new list needed — CS and leadership share this
# one.
_CS_SECONDARY_METRICS = ['stat_active', 'stat_pending', 'due', 'clashes', 'stat_avg_time']

# Tab order, per role. _STAT_TILES is always last (see the big comment
# above). The rest is a judgment call, easy to change later since it's
# just a list.
#
# 'summary' REMOVED from every list (15 Jul 2026, later still) — see the
# big comment above. 'due'/'at_risk' REMOVED from every list earlier the
# same day, per Ezekiel: "Move overdue and at risk down, so they are
# always visible, the interactive area goes below. Also remove their
# cards since it will be redundant" — Overdue and At Risk are no longer
# tabs at all. `due_default`/`at_risk_projects`/`due_today_items`/
# `due_week_items` are still computed in index() exactly as before — only
# WHERE they render changed (now the two toggle boxes above the tab
# strip — see dashboard.html), not what data feeds them.
# 'brief_quality' moved to the very end (15 Jul 2026, later still) — per
# Ezekiel: "Move average brief quality to the end." Was positioned right
# before the stat tiles in every role's list; now it's after them, so
# it's the last tab, full stop, in every role's tab strip.
CARD_ORDER = {
    'management': ['decisions', 'what_changed', 'next_actions', 'clashes'] + _STAT_TILES + ['brief_quality'],
    'admin':      ['decisions', 'what_changed', 'next_actions', 'clashes'] + _STAT_TILES + ['brief_quality'],
    'cs':         ['decisions', 'what_changed', 'next_actions', 'clashes'] + _STAT_TILES + ['brief_quality'],
    'designer':   ['clashes', 'decisions', 'what_changed', 'next_actions'] + _STAT_TILES + ['brief_quality'],
    'team_lead':  ['clashes', 'decisions', 'what_changed', 'next_actions'] + _STAT_TILES + ['brief_quality'],
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
      'designer_<id>' (added 15 Jul 2026, per Ezekiel: "add the designers
             also to management/admin view as tabs"; widened 16 Jul 2026,
             per Ezekiel: "the designer button should show all designers
             and team leads, right now it only shows designers" — despite
             the name, this branch has always covered BOTH roles that
             live on ProjectDesigner assignments) — exactly what that
             designer's or team lead's own dashboard shows them. Same idea
             as 'cs_<id>', but scoped via _ScopeUser(target.id,
             target.role) — target.role is whichever of 'designer'/
             'team_lead' this particular user actually has, NOT a
             hardcoded 'designer' (that would have been harmless today,
             since _scoped_projects() lumps both into one shared "designer
             / team_lead" branch by exclusion, and CARD_ORDER's 'designer'
             and 'team_lead' entries are currently identical lists — but
             hardcoding it was still a latent footgun for the day either
             of those two things stops being true) — so _scoped_projects()
             falls into its designer/team_lead branch (ProjectDesigner
             assignment) instead of the CS one. Decisions stays normally
             scoped here too, same reasoning as 'cs_<id>'.
      'all' — today's original behaviour: everything, unfiltered.

    Returns (scope_mode, scope_user, cs_leads, designers) — cs_leads (every
    role='cs' user) and designers (every user with role='designer' OR
    role='team_lead', widened 16 Jul 2026 alongside the 'designer_<id>'
    branch above — see that entry's docstring), for building one tab per
    lead/designer/team-lead, are returned even when scope_mode is None
    since dashboard.html needs them any time it's rendering for a
    management/admin user, and computing them here once is cheaper than
    every caller re-querying them.
    """
    cs_leads = User.query.filter_by(role='cs').order_by(User.name.asc()).all()
    designers = User.query.filter(User.role.in_(['designer', 'team_lead'])).order_by(User.name.asc()).all()

    if user.role not in _SCOPE_SWITCHER_ROLES:
        return None, user, cs_leads, designers

    # Default changed 'my' -> 'all' on 16 Jul 2026, per Ezekiel: "Right now
    # management and admin it only shows their overdue products, and their
    # project clashes. I need it to show ALL of them across all projects."
    # Root cause: dashboard_leadership.html no longer includes
    # _view_switcher.html (removed earlier the same day), so there is no UI
    # left that can ever send ?scope=all — every management/admin page load
    # was silently falling through to 'my' (their own CS-lead slice, almost
    # always near-empty for these roles) instead of the company-wide view
    # this dashboard is meant to show them. The 'my'/'cs_<id>'/'designer_<id>'
    # branches below are all still fully intact for any future UI (e.g. a
    # resurrected view-switcher) that wants to request them explicitly via
    # ?scope=... — only the no-param default changed.
    requested = request.args.get('scope', 'all')

    if requested == 'all':
        return 'all', user, cs_leads, designers

    if requested.startswith('cs_'):
        try:
            target_id = int(requested[3:])
        except ValueError:
            target_id = None
        target = next((c for c in cs_leads if c.id == target_id), None)
        if target:
            return requested, _ScopeUser(target.id, 'cs'), cs_leads, designers
        # Unknown/stale id (e.g. a CS lead removed since this URL/tab was
        # bookmarked) — fall through to 'my' rather than 403ing or
        # silently rendering the full unfiltered 'all' view.

    if requested.startswith('designer_'):
        try:
            target_id = int(requested[len('designer_'):])
        except ValueError:
            target_id = None
        target = next((d for d in designers if d.id == target_id), None)
        if target:
            return requested, _ScopeUser(target.id, target.role), cs_leads, designers
        # Same stale-id fallback as the cs_ branch above.

    return 'my', _ScopeUser(user.id, 'cs'), cs_leads, designers


@dashboard_bp.route('')
@login_required
def index():
    user = get_actor()
    initial_view = request.args.get('view', '')
    scope_mode, scope_user, cs_leads, designers = _resolve_dashboard_scope(user)

    # Card order normally follows the REAL role. Exception: previewing a
    # specific CS lead's, designer's, or team lead's tab should look like
    # their actual dashboard, ordering included — not management's own
    # layout with someone else's data dropped into it. 'my' mode keeps
    # management's own order (it's still fundamentally "my dashboard",
    # just narrowed), only 'cs_<id>'/'designer_<id>' borrow that role's
    # own order.
    #
    # layout_role = scope_user.role (not a hardcoded 'designer') as of 16
    # Jul 2026 — the designer_<id> branch now covers team leads too (see
    # _resolve_dashboard_scope()'s docstring), so a previewed team lead
    # correctly borrows CARD_ORDER['team_lead'] instead of always
    # CARD_ORDER['designer']. The two lists happen to be identical today,
    # so this had no visible effect before, but reading the real role off
    # scope_user is the correct fix rather than relying on that
    # coincidence staying true.
    if (scope_mode or '').startswith('cs_'):
        layout_role = 'cs'
    elif (scope_mode or '').startswith('designer_'):
        layout_role = scope_user.role
    else:
        layout_role = user.role

    # Average Project Time's inline body used to eagerly call
    # build_time_tracking_rows() right here, on EVERY dashboard page load
    # for admin/management — REMOVED 18 Jul 2026, real perf bug, not a
    # style choice. That function does a full company-wide scan (every
    # non-draft project, then for EACH one, its own project_deliverables
    # lazy relationship, then for EACH deliverable, its own status_logs
    # lazy relationship, plus a business-hours calculation per project and
    # per deliverable) — an N+1 storm that ran whether or not the user
    # ever opened this tab, and was the dominant cost behind a 3+ second
    # dashboard load reported by Ezekiel (screenshot showed the main HTML
    # request alone taking 3.27s). Now computed lazily, only when the tab
    # is actually clicked, via GET /dashboard/api/time-tracking-rows (see
    # that route further down + stat_avg_time.html/dashboard.js for the
    # fetch-on-first-open wiring). stat_avg_time.html no longer takes a
    # time_tracking_rows kwarg at all — it only needs `is_openable`
    # (effective_role in ('admin','management')), computed inside the
    # template itself, unchanged.
    card_order = CARD_ORDER.get(layout_role, CARD_ORDER['management'])

    # ── CS-only redesigned dashboard branch (16 Jul 2026) ─────────────────
    # Per Ezekiel, sharing a mockup screenshot: "Can we redesign it to be
    # something like this?" — see the big comment above
    # _serialize_owners_list() (further down this file) for the full design
    # history and _compute_priority_actions()/_compute_waiting_on_others()'s
    # own docstrings for what replaces Next Actions' old My/Others toggle
    # and the now-retired At Risk card.
    #
    # Keyed on layout_role, not user.role directly — a management/admin
    # user previewing a CS lead's scope-switcher tab (scope_mode starting
    # with 'cs_') also gets this new layout, matching every other "borrow
    # that role's own page" rule layout_role already drives above (the
    # CARD_ORDER lookup just above, get_next_action_owner()'s guidance,
    # etc.) — previewing a CS lead should look like THEIR dashboard,
    # layout included, not the management user's own page with someone
    # else's data dropped in. Every other role/scope combination
    # (designer/team_lead always, management/admin's own 'my'/'all'/
    # 'designer_<id>' views) falls through to the unchanged dashboard.html
    # below.
    #
    # cs_leads/designers/scope_mode are still passed through even though a
    # REAL CS user never sees the view-switcher UI itself (effective_role
    # gates that in dashboard_cs.html, same as dashboard.html) — a
    # management/admin user landing here via a cs_<id> preview still needs
    # the view-switcher rendered so they can navigate to a different tab or
    # back to their own view.
    if layout_role == 'cs':
        return render_template(
            'dashboard_cs.html',
            effective_role=user.role,
            scope_mode=scope_mode,
            cs_leads=cs_leads,
            designers=designers,
            # dash_cs_layout=True is read by the two reused secondary-metric
            # partials (due.html, clashes.html) for the one wording tweak
            # this layout needs — see clashes.html's clashes_title.
            dash_cs_layout=True,
            summary=_compute_summary(scope_user),
            priority_actions=_compute_priority_actions(scope_user),
            waiting_on_others=_compute_waiting_on_others(scope_user),
            my_escalated_projects=_compute_my_escalated_projects(scope_user),
            my_escalation_history=_compute_my_escalation_history(scope_user),
            # due_today (16 Jul 2026) — feeds the newly-clickable "X due
            # today" Focus pill's expandable section (see dash_due_today_
            # row() in _dashboard_macros.html). Reuses _compute_due()'s
            # existing 'today' filter_type AS-IS — same data
            # summary.due_today's count is already derived from
            # (_compute_summary() computes that count as
            # len(_compute_due(user, 'today')), see its own docstring), so
            # the pill's number and the list it opens can never disagree.
            due_today=_compute_due(scope_user, 'today'),
            what_changed=_compute_what_changed(scope_user),
            secondary_metrics_order=_CS_SECONDARY_METRICS,
            initial_expanded_card=None,
            project_stats=_compute_project_stats(scope_user),
            your_active_projects=_compute_your_active_projects(scope_user),
            pending_approval_projects=_compute_pending_approval_projects(scope_user),
            due_default=_compute_due(scope_user, 'overdue'),
            clashes=_compute_clashes_response(scope_user),
            flaggable_projects=_compute_flaggable_projects(user),
        )

    # ── Leadership dashboard branch (management/admin, 16 Jul 2026) ───────
    # See the big comment above _compute_risk_overdue() (further down this
    # file) for the full design history. Keyed on layout_role, same
    # "borrow that role's own page" rule the CS branch above already
    # follows — a management/admin user's own 'my'/'all' tabs keep
    # layout_role == their real role, so both land here; previewing a
    # specific cs_<id>/designer_<id> tab already returned above (CS
    # branch) or falls through to the designer/team_lead render below.
    # Admin gets this SAME layout for now too, per Ezekiel: "again admin
    # dashboard we will develop tmw which will be more about app health,
    # server health etc, but for now I will see what management sees."
    if layout_role in ('management', 'admin'):
        decisions = _compute_decisions(scope_user, all_flags=True)
        risk_overdue = _compute_risk_overdue(scope_user)
        return render_template(
            'dashboard_leadership.html',
            effective_role=user.role,
            scope_mode=scope_mode,
            cs_leads=cs_leads,
            designers=designers,
            decisions=decisions,
            risk_overdue=risk_overdue,
            # Escalation History (17 Jul 2026) — joins decisions/role_
            # snapshot's "always company-wide, not part of the All/Focused
            # toggle" group (risk_overdue/waiting_on_others below ARE
            # scope_user-aware — see _compute_escalation_history()'s own
            # docstring for why this one isn't). Takes no scope argument at
            # all.
            escalation_history=_compute_escalation_history(),
            waiting_on_others=_compute_leadership_waiting_on_others(scope_user),
            role_snapshot=_compute_role_snapshot(),
            leadership_focus=_compute_leadership_focus(scope_user, len(decisions), risk_overdue),
            # Plain {id, name, team} dicts (not raw User objects — those
            # aren't JSON-serializable via Jinja's |tojson) for the Assign
            # Designer modal's client-side team-filter, embedded as a
            # script-block constant per CLAUDE.md's "JS in templates —
            # JSON data" rule.
            designers_for_assign=[{'id': u.id, 'name': u.name, 'team': u.team} for u in designers],
            # Secondary Metrics row (16 Jul 2026, later still) — per
            # Ezekiel, sharing a screenshot of the CS dashboard's own
            # Secondary Metrics tiles: "add this to the management view
            # also, at the bottom." Reuses _CS_SECONDARY_METRICS as-is
            # (renamed in spirit, not in code — see that constant's own
            # comment, which now also documents this second consumer) and
            # the exact same dash_card() tab+body mechanic/data every
            # field here already feeds on the CS layout. dash_cs_layout=
            # True is reused for clashes.html's "Deadline Clashes" vs
            # "Clashing Projects" title switch too — see that file's
            # updated comment; the flag really means "new-style Secondary
            # Metrics layout", not "CS specifically", it just didn't have
            # a second consumer until now.
            dash_cs_layout=True,
            secondary_metrics_order=_CS_SECONDARY_METRICS,
            # Every one of the 5 Secondary Metrics partials' dash_card()
            # call reads initial_expanded_card (expanded=(initial_expanded_
            # card == '<key>')) — also missed on the first pass, same class
            # of bug as the summary= omission below. None here for the same
            # reason dashboard_cs.html's branch passes None: this page has
            # no ?view= deep-link support for these tabs, so nothing should
            # be pre-expanded on load.
            initial_expanded_card=None,
            # due.html's mini-stat reads summary.overdue for its red/green
            # colour (see the big comment above _compute_summary() — the
            # same function dashboard_cs.html's branch already passes this
            # under). Missed on the first pass of this addition, causing a
            # live jinja2.exceptions.UndefinedError: 'summary' is undefined
            # the moment a management/admin user loaded the page — due.html
            # is one of the 5 reused Secondary Metrics partials but wasn't
            # part of this page's payload before today.
            summary=_compute_summary(scope_user),
            project_stats=_compute_project_stats(scope_user),
            your_active_projects=_compute_your_active_projects(scope_user),
            pending_approval_projects=_compute_pending_approval_projects(scope_user),
            due_default=_compute_due(scope_user, 'overdue'),
            clashes=_compute_clashes_response(scope_user),
        )

    # ── Designer / Team Lead dashboard branch (16 Jul 2026) ───────────────
    # See the big comment above _compute_designer_work_queue() (further
    # down this file) for the full design history. Keyed on layout_role,
    # same "borrow that role's own page" rule the CS/leadership branches
    # above already follow — a real designer/team_lead's own 'my' scope
    # keeps layout_role == their real role, so both land here; a
    # management/admin user previewing a designer_<id> tab also lands here
    # (layout_role = scope_user.role, see _resolve_dashboard_scope()) —
    # exactly the "previewing a designer should look like THEIR dashboard"
    # rule the view-switcher was built for. work_queue/metrics are computed
    # once here and threaded into both focus= and template= kwargs, same
    # "don't re-query what's already fetched" rule _compute_leadership_
    # focus() follows for its own bar.
    if layout_role in ('designer', 'team_lead'):
        work_queue = _compute_designer_work_queue(scope_user)
        metrics = _compute_designer_metrics(scope_user)
        return render_template(
            'dashboard_designer.html',
            effective_role=user.role,
            scope_mode=scope_mode,
            cs_leads=cs_leads,
            designers=designers,
            focus=_compute_designer_focus(work_queue, metrics),
            work_queue=work_queue,
            waiting_on_others=_compute_waiting_on_others(scope_user),
            week_load=_compute_designer_week_load(scope_user),
            metrics=metrics,
        )

    return render_template(
        'dashboard.html',
        effective_role=user.role,
        scope_mode=scope_mode,
        cs_leads=cs_leads,
        designers=designers,
        card_order=card_order,
        # Which tab is active on first paint. Used to default to 'summary'
        # (My Day/My Week) — REMOVED 15 Jul 2026, later still, along with
        # 'summary' from CARD_ORDER itself (see the big comment above it):
        # My Day/My Week is now its own always-open toggle box, not a tab,
        # so there's no more fixed "always this one" default. Briefly
        # fell back to `card_order[0]` (auto-expanding the first tab) —
        # REMOVED AGAIN 16 Jul 2026, per Ezekiel: "have it hidden until a
        # user selects a tab." No fallback at all now: if `?view=` doesn't
        # map to a real card (VIEW_TO_CARD), this is None, every card
        # partial's `expanded=(initial_expanded_card == '<key>')` check is
        # False for all of them, .dash-content-area has nothing to show
        # (see its own docstring below), and the page loads with the
        # content area genuinely empty until the user clicks a tab.
        initial_expanded_card=VIEW_TO_CARD.get(initial_view),
        # Feeds the stat cards' badges (stat_active/stat_pending/
        # stat_avg_time — see the big comment above CARD_ORDER) — see
        # _compute_project_stats()'s docstring for the scoping rules.
        project_stats=_compute_project_stats(scope_user),
        # Row-list BODIES for the two simple stat cards (added 15 Jul
        # 2026, same day those cards moved into the tab strip) — each is
        # the exact same _scoped_projects() query _compute_project_stats()
        # counts for that number, just serialized into full rows instead
        # of a bare count. total_active_projects/_compute_total_active_
        # projects() REMOVED same day, later still, per Ezekiel: "Remove
        # total active projects also."
        your_active_projects=_compute_your_active_projects(scope_user),
        pending_approval_projects=_compute_pending_approval_projects(scope_user),
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
        # Only CS/Designer/Team Lead ever see the "Escalate" button (renamed
        # from "Flag a Project" 16 Jul 2026 — see decisions.html)
        # (Management has no reason to flag something to itself), so skip
        # the extra query entirely for roles that can't open the modal.
        # Deliberately keyed on the REAL user.role, not layout_role/scope —
        # previewing a CS lead's tab must never grant management the
        # ability to submit a flag as that person.
        flaggable_projects=_compute_flaggable_projects(user) if user.role in ('cs', 'designer', 'team_lead') else [],
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
    missing_teams = _missing_designer_teams(project)
    if not missing_teams:
        return []

    if len(missing_teams) == len(_requested_teams_list(project)):
        return ['All Designers Missing']

    return [_TEAM_MISSING_LABELS.get(t, f'{t} Missing') for t in missing_teams]


def _requested_teams_list(project):
    """Plain list of a project's requested design teams (parsed CSV), no
    staffing check — shared helper so _missing_designer_teams() and any
    caller needing "what teams did this project ask for" don't each
    re-split project.design_teams_requested their own way."""
    return [t.strip() for t in (project.design_teams_requested or '').split(',') if t.strip()]


def _missing_designer_teams(project):
    """
    RAW list of team names (e.g. ['3D', 'Technical']) missing a
    project-level Lead Designer — the same check _missing_designer_tags()
    above already made, pulled out one level further (16 Jul 2026, for the
    leadership dashboard's Risk/Overdue card and its "Assign Designer"
    button) so a caller that needs the actual team names to scope a
    designer picker isn't stuck parsing _missing_designer_tags()' rendered
    label strings (which collapse to 'All Designers Missing' and lose the
    individual team names once every team is unstaffed). Returns [] for a
    fully-staffed or team-less project, same as _missing_designer_tags().
    """
    requested_teams = _requested_teams_list(project)
    if not requested_teams:
        return []
    assigned_teams = {d.team for d in project.assigned_designers}
    return [t for t in requested_teams if t not in assigned_teams]


# Statuses meaning "this work has left the design team's hands and is
# sitting with CS/client for review or a response" — 17 Jul 2026, per
# Ezekiel: "the dashboard overdue sections needs to ignore deadlines if
# the project is in submitted stage... these are just visible in waiting
# on others only." Shared by Project.project_status AND Deliverable.status
# (both use the same status vocabulary — see the status_map rebuild note
# in CLAUDE.md). Deliberately does NOT include 'approved'/'internal_revision'
# /'revision_in_queue'/'revision_in_progress' — a revision means the ball
# is back in the design team's court, so a revision deadline slipping is a
# real, actionable Overdue, not something waiting on someone else.
_SUBMITTED_STAGE_STATUSES = {'submitted', 'internal_review', 'submitted_to_client'}


def _customer_is_submitted_stage(pc):
    """
    True if a C&CM customer's design work is at/past submitted stage —
    i.e. it should never be flagged Overdue, only ever surface via
    Waiting on Others. ProjectCustomer.status itself is NOT a reliable
    signal for this (see CLAUDE.md's status-tracking notes — it's only
    ever written at customer creation and via the manual admin override
    route in projects_detail.py, never auto-advanced by the real
    submission/POSM flow). The customer's own Deliverable rows
    (Deliverable.project_customer_id == pc.id), however, ARE reliably
    advanced by record_deliverable_status() throughout the POSM/channel
    submission flow — so this checks those instead. A customer with no
    deliverables of its own yet is never "submitted" (nothing to submit).
    JUDGMENT CALL: requires EVERY one of the customer's deliverables to be
    at submitted-stage-or-beyond (not just any one), since a customer
    whose deliverables are only partially submitted still has real,
    actionable outstanding design work.
    """
    deliverables = pc.deliverables
    if not deliverables:
        return False
    return all(d.status in _SUBMITTED_STAGE_STATUSES or d.status == 'approved' for d in deliverables)


_DUBAI_TZ = timezone(timedelta(hours=4))


def _format_waiting_date(dt):
    """
    "Waiting since" display text (added 16 Jul 2026, for the Decisions
    Needed / Next Actions "Others'" waiting-info feature below) — a short
    day+month string, e.g. "13 Jul", no year and no time-of-day (contrast
    with the `dubai_time` Jinja filter in app/__init__.py, which renders a
    full timestamp). Converts the stored UTC datetime to Dubai local time
    first via the same fixed `timezone(timedelta(hours=4))` offset every
    other Dubai-local date/time calculation in this codebase uses (see
    CLAUDE.md's DB Facts — ZoneInfo needs tzdata, not reliably present on
    the Windows dev box) — without this, a status change or flag raised
    late at night UTC could display as the wrong calendar day.
    """
    if not dt:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(_DUBAI_TZ).strftime('%d %b')


def _compute_at_risk_projects(user):
    """
    "At Risk" card (added 12 Jul 2026, per management review). NOT the same
    thing as the dashboard's now-removed deep-dive zone, which used to have
    its own separate BriefFlag/decision/RAG-red filter (_is_at_risk(),
    deleted 13 Jul 2026 along with that whole section — see CLAUDE.md) —
    this is a staffing-gap + overdue check, one row per project, each row
    carrying whichever tags apply:

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

    # Nearest deadline first, same convention every dashboard row list uses
    # — projects with no deadline at all sort last.
    results.sort(key=lambda r: r['deadline'] or '9999-12-31')
    return results


def _compute_summary(user):
    active_projects = _scoped_projects(user, active_only=True).all()
    today = date.today()  # still needed below for what_changed's yesterday cutoff

    # due_today/due_week/overdue counts — FIXED 15 Jul 2026 (same day as the
    # pinned Overdue/At Risk work above): these used to be counted with a
    # separate per-project loop keyed on nearest_deadline(p), i.e. ONE
    # deadline per project — so a project with 2 overdue deliverables only
    # ever contributed 1 to `overdue`. That silently disagreed with the
    # actual "Overdue" list (due.html's #dash-due-list, from
    # _compute_due(user, 'overdue')), which is deliverable/customer-granular
    # and correctly listed both. Caught live: the badge read "1" while the
    # expanded card listed 8+ rows for the same scope. due_today_items/
    # due_week_items (Summary's own two columns, just below these very
    # mini-stats — see summary.html) ALREADY used _compute_due() under the
    # hood, so this fix just makes the collapsed NUMBER agree with the
    # expanded LIST everywhere on this page, using _compute_due() itself as
    # the one source of truth for all three counts instead of a second,
    # coarser reimplementation.
    due_today = len(_compute_due(user, 'today'))
    due_week = len(_compute_due(user, 'week'))
    overdue = len(_compute_due(user, 'overdue'))

    my_actions = others_actions = 0
    for p in active_projects:
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


def _stat_project_rows(projects):
    """
    Shared row-serializer for the three simple stat cards' bodies (Your
    Active / Pending Approval / Total Active — added 15 Jul 2026 when they
    moved from static tiles into real tab+body cards, see the big comment
    above CARD_ORDER). Deliberately plain — just enough for a membership
    list ("which projects make up this number"), not an actionable row
    like Due/Next Actions, so no cs_lead/designers/guidance fields here.

    status_label uses the exact same `.replace('_', ' ').title()` pattern
    api.py's own status_label already uses for this — same display
    convention, not a new one invented for this card.
    """
    rows = [{
        'project_id': p.id,
        'name': p.name,
        'deadline': (lambda d: d.isoformat() if d else None)(nearest_deadline(p)),
        'status_label': (p.project_status or '').replace('_', ' ').title(),
    } for p in projects]
    # Nearest deadline first, no-deadline last — same convention every
    # other row list on this page sorts by (see _compute_at_risk_projects()
    # etc.).
    rows.sort(key=lambda r: r['deadline'] or '9999-12-31')
    return rows


def _compute_your_active_projects(user):
    """Body for the 'Your Active Projects' stat card — the exact same
    _scoped_projects(user, active_only=True) query _compute_project_stats()
    counts for 'your_active', now serialized into full rows."""
    return _stat_project_rows(_scoped_projects(user, active_only=True).all())


def _compute_pending_approval_projects(user):
    """Body for the 'Pending Approval' stat card — same query
    _compute_project_stats() counts for 'pending_approval'."""
    return _stat_project_rows(
        _scoped_projects(user, active_only=True)
        .filter(Project.project_status == 'submitted_to_client').all()
    )


# _compute_total_active_projects() REMOVED 15 Jul 2026, later still, per
# Ezekiel: "Remove total active projects also" — used to return the body
# for the 'Total Active Projects' stat card (same UNSCOPED query
# _compute_project_stats() below still counts for its 'total_active'
# badge number). That badge number itself is LEFT IN _compute_project_
# stats()'s return dict below rather than torn out — it's still computed
# there for the /api/project-stats SSE endpoint's response shape, and
# leaving one unused dict key is harmless where surgically narrowing a
# shared, multi-consumer function's return contract is not. stat_total.html,
# the 'stat_total' entry in _STAT_TILES, and the total_active_projects=
# kwarg this function used to feed were all removed in the same pass — see
# CLAUDE.md for the full list of what changed.


def _compute_project_stats(user):
    """
    Badge numbers for the stat cards — Your Active Projects / Pending
    Approval / Average Project Time, always LAST in CARD_ORDER (see
    _STAT_TILES above). Still returns a 'total_active' key too (see the
    comment just above this function) even though 'stat_total' itself was
    removed 15 Jul 2026 — nothing renders it anymore, kept only because
    this dict also feeds the /api/project-stats SSE endpoint's response
    shape. Added 12-13 Jul 2026 as a separate non-interactive stat row;
    moved down into ordinary dash_card() tab+body cards 15 Jul 2026 (see
    the big comment above CARD_ORDER) — this function still only returns
    the bare numbers for each card's badge. The two simple cards' actual
    BODY content (a project list) comes from the sibling
    _compute_your_active_projects()/_compute_pending_approval_projects()
    functions above, which deliberately re-run the same underlying
    queries rather than reshaping this function's output, matching the
    "each card independently re-queries _scoped_projects()" convention
    every other card on this page already follows. Average Project Time's
    body (admin/management only) comes from build_time_tracking_rows() —
    NOT fetched in index() anymore (18 Jul 2026 perf fix, see the big
    comment there) — now lazy-loaded client-side via GET /dashboard/api/
    time-tracking-rows only when the tab is actually opened.
    This function still feeds both the initial page load and the SSE
    live-refresh's /api/project-stats fetch (badges only, never bodies —
    see dashboard.js).

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
    _, scope_user, _, _ = _resolve_dashboard_scope(get_actor())
    return jsonify(_compute_project_stats(scope_user))


@dashboard_bp.route('/api/summary')
@login_required
def api_summary():
    # Scope-aware since 11 Jul 2026 (management view-switcher) — the SSE
    # live-refresh in dashboard.js hits this endpoint with whatever
    # ?scope= the page currently has loaded (see HELIX_DASH_SCOPE in
    # dashboard.html) so the collapsed pills never drift back to the
    # unfiltered view mid-session. See _resolve_dashboard_scope().
    _, scope_user, _, _ = _resolve_dashboard_scope(get_actor())
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
    _, scope_user, _, _ = _resolve_dashboard_scope(get_actor())
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

    17 Jul 2026, per Ezekiel: an 'overdue'/'overdue_today' row is SKIPPED
    (never appended) when the underlying deliverable/customer/project is
    already at submitted stage (see _SUBMITTED_STAGE_STATUSES) — that work
    has left the design team's hands, so a late DESIGN deadline no longer
    means anything is actually overdue; it should only ever surface via
    Waiting on Others (_compute_waiting_on_others() /
    _compute_leadership_waiting_on_others()), never an Overdue tag/bucket.
    'today'/'week' filters are unaffected — a submitted item is still
    correctly informational there.
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

    # 17 Jul 2026, per Ezekiel: "the dashboard overdue sections needs to
    # ignore deadlines if the project is in submitted stage... these are
    # just visible in waiting on others only." Only applied for the two
    # OVERDUE filter values — 'today'/'week' are untouched, since a
    # not-yet-submitted deliverable due today should still show as due
    # today regardless of another row's submission stage.
    is_overdue_filter = filter_type in ('overdue', 'overdue_today')

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
            # guidance_for_viewer() (15 Jul 2026, per Ezekiel — see
            # dashboard_logic.py's docstring) swaps CS-role guidance for a
            # flat "No action required" when `user` (the scope_user this
            # whole function was called with) is a designer/team lead —
            # owner['guidance'] itself is untouched, still the real
            # role-neutral text.
            'rag': rag, 'owner': owner_json, 'owner_role': owner['role'],
            'guidance': guidance_for_viewer(owner, user),
            'cs_lead': cs_lead_json,
            # owner_chips (16 Jul 2026, for the CS dashboard's clickable
            # "due today" Focus pill — see dash_due_today_row() in
            # _dashboard_macros.html) — reuses _serialize_owners_list()
            # AS-IS (already built for Waiting on Others' identical "who's
            # turn is it right now, could be 0/1/several people" need), so
            # this row carries BOTH the existing cs_lead+designers pair
            # (still used by dash_due_row() elsewhere) and this single
            # current-owner chip list, without the two ever needing to
            # agree — "who's assigned" and "whose turn it currently is"
            # are different questions.
            'owner_chips': _serialize_owners_list(owner['user']),
        }

        if p.brief_type == 'ccm':
            for pc in p.project_customers:
                if pc.cancelled or pc.status == 'approved':
                    continue
                if is_overdue_filter and _customer_is_submitted_stage(pc):
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
                    # Submitted-stage exclusion is checked AFTER
                    # matched_any_deliverable is set — a project-level
                    # fallback row still shouldn't fire just because its
                    # only matching deliverable happened to be excluded
                    # here; that deliverable-level deadline still "counts"
                    # for the purposes of deciding granularity, it's just
                    # not itself flagged Overdue while submitted.
                    if is_overdue_filter and d.status in _SUBMITTED_STAGE_STATUSES:
                        continue
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
            if (not matched_any_deliverable and matches(p.execution_date)
                    and not (is_overdue_filter and p.project_status in _SUBMITTED_STAGE_STATUSES)):
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
    _, scope_user, _, _ = _resolve_dashboard_scope(get_actor())
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

    'waiting_since_display' / 'waiting_reason' / 'waiting_color' (added 16
    Jul 2026, per Ezekiel: "For every item in Decision Needed / Others'
    Actions, show: Waiting since... Waiting for... Use red only for:...
    senior decision blocking work") — every row here already IS "senior
    decision blocking work" by definition (that's what decision_needed=True
    means), so waiting_color is unconditionally 'red', no per-row
    classification needed the way Next Actions requires below.
    waiting_since_display is decision_raised_at reformatted via
    _format_waiting_date() (day+month, Dubai-local — see that function).
    waiting_reason surfaces the SAME missing-designer check At Risk/Next
    Actions/Clashes already use (_missing_designer_tags()) as plain text
    ("Designer assignment") rather than a list of per-team tags — this
    card has no person-chip row to show those in, so a short reason string
    is the more useful signal in-place; only set when the project actually
    has an unstaffed requested team, per Ezekiel's "(if relevant)".
    """
    if all_flags:
        base = Project.query.filter(Project.project_status != 'draft')
    else:
        base = _scoped_projects(user, active_only=True)

    projects = base.filter(Project.decision_needed.is_(True)).all()

    now = datetime.utcnow()

    # Switched from ordering by the deprecated Project.decision_raised_at
    # column to sorting on each project's active DecisionFlag.created_at
    # instead (17 Jul 2026, Decision Flag reply/resolve feature) — that
    # column stopped being written to once flag_management() started
    # creating DecisionFlag rows instead (see that route), so ordering by
    # it would now be sorting on a value that's always NULL for every new
    # flag. Paired up once per project (the active_decision_flag property
    # itself queries, so this avoids doing it twice — once to sort, once
    # to build the row below). A decision_needed=True project with no
    # matching flag row is defensively skipped rather than crashing on
    # flag.note — the two are separate signals (fast boolean sentinel vs.
    # rich row) that could in theory drift, per active_decision_flag's own
    # docstring in app/models/__init__.py.
    pairs = [(p, p.active_decision_flag) for p in projects]
    pairs = [(p, f) for p, f in pairs if f is not None]
    pairs.sort(key=lambda pf: pf[1].created_at or datetime.max)

    return [
        {
            'project_id': p.id,
            'project_name': p.name,
            # Switched from _serialize_user() to _serialize_person() 16 Jul
            # 2026 (same-day follow-up, per Ezekiel: "the name tag should
            # follow our image + name system we are using everywhere else
            # on the dashboard") — carries avatar_filename so dash_person_
            # chip()/personChip() can render an avatar+name chip instead of
            # a plain text .dash-owner-tag pill. Harmless superset for
            # decisions.html's own still-unchanged raised_by usage (that
            # template only ever read .name).
            'raised_by': _serialize_person(flag.created_by),
            'raised_at': flag.created_at.isoformat() if flag.created_at else None,
            'note': flag.note,
            'days_waiting': (now - flag.created_at).days if flag.created_at else None,
            'waiting_since_display': _format_waiting_date(flag.created_at),
            'waiting_reason': 'Designer assignment' if _missing_designer_tags(p) else None,
            'waiting_color': 'red',
            # Surfaced 17 Jul 2026 so decisions.html/dashboard_leadership.html
            # can show a reply-count badge and open the shared Decision Flag
            # modal directly from this row instead of only offering an
            # instant-fire Resolve button.
            'flag_id': flag.id,
            'reply_count': len(flag.messages),
        }
        for p, flag in pairs
    ]


@dashboard_bp.route('/api/decisions')
@login_required
def api_decisions():
    scope_mode, scope_user, _, _ = _resolve_dashboard_scope(get_actor())
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

    'waiting_since_display' / 'waiting_reason' / 'waiting_color' (added 16
    Jul 2026, per Ezekiel: "For every item in Decision Needed / Others'
    Actions, show: Waiting since... Waiting for..."; widened the same day,
    per Ezekiel's follow-up: "Apply those changes to the my actions tab
    too, it's only on other's actions") — computed for EVERY row
    regardless of filter_type (cheap, and keeps the 'mine'/'others'
    payloads structurally identical), and now RENDERED on both tabs too.
    dash_due_row()'s show_waiting param still defaults to False (Overdue/
    Today/This Week never pass it), but both Next Actions render paths now
    pass True: next_actions.html's SSR 'mine' list passes show_waiting=True
    directly, and fetchAndRenderNextActions() passes showWaiting=true to
    renderDueRow() unconditionally (both filter values) — see
    dashboard.js.

    waiting_since_display: the started_at of the project's CURRENTLY OPEN
    ProjectStatusLog row (ended_at is None — there's always exactly one,
    per record_project_status()'s own invariant, see status_tracking.py) —
    i.e. since the project landed in the status that produced the CURRENT
    next-action guidance, not since the project was created. Falls back to
    None (nothing rendered) in the unexpected case no open row exists.

    waiting_color classification (maps the 8 reasons from Ezekiel's spec
    onto data this page already computes, skipping the two with no
    reliable signal yet — "due soon" has no defined threshold, "incomplete
    brief" has no tracked concept — per explicit instruction to leave
    those out rather than guess):
      RED   — overdue (deadline has passed) OR missing critical owner
              (no CS lead, defensively — see _compute_at_risk_projects()'s
              own comment on why this can't actually fire yet — OR any
              requested design team unstaffed, same bar the red
              missing-designer chips elsewhere on this page already use)
      AMBER — everything else: no deadline, or just plain "waiting on
              whoever's turn it is" with nothing more specific wrong.
    waiting_reason is set to 'Designer assignment' whenever ANY requested
    team is missing (derived from the SAME `designers` list already built
    below via _due_row_people() — not a second query — so this can never
    disagree with the red chips the row itself renders).
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
        designers = _due_row_people(p, requested_teams)
        has_missing_designer = any(not team['users'] for team in designers)
        is_overdue = bool(deadline) and deadline < date.today()
        has_no_cs_lead = not p.cs_lead_id
        waiting_since = next((sl.started_at for sl in p.status_logs if sl.ended_at is None), None)
        results.append({
            'project_id': p.id,
            'type': 'project',
            'project_name': p.name,
            # guidance_for_viewer() (15 Jul 2026) — same swap as
            # _compute_due() above: designer/team-lead viewers see "No
            # action required" for a CS-role next action instead of text
            # like "Follow up with client" they can't act on.
            'guidance': guidance_for_viewer(owner_info, user),
            'owner': _serialize_owner(owner_info['user']),
            'owner_role': owner_info['role'],
            'rag': get_project_rag(p),
            'deadline': deadline.isoformat() if deadline else None,
            'cs_lead': _serialize_person(p.cs_lead),
            'designers': designers,
            'waiting_since_display': _format_waiting_date(waiting_since),
            'waiting_reason': 'Designer assignment' if has_missing_designer else None,
            'waiting_color': 'red' if (is_overdue or has_no_cs_lead or has_missing_designer) else 'amber',
        })

    results.sort(key=lambda r: r['deadline'] or '9999-12-31')
    return results


@dashboard_bp.route('/api/next-actions')
@login_required
def api_next_actions():
    _, scope_user, _, _ = _resolve_dashboard_scope(get_actor())
    filter_type = request.args.get('filter', 'mine')
    return jsonify(_compute_next_actions(scope_user, filter_type))


# ── CS-only redesigned dashboard (16 Jul 2026) ──────────────────────────
# Per Ezekiel, sharing a mockup screenshot of a much simpler layout —
# "Can we redesign it to be something like this?" Clarified via
# AskUserQuestion + two follow-up messages into a specific spec: full
# replacement of the tab-strip/toggle-box layout, but CS ROLE ONLY for
# now (management/admin/designer/team_lead keep the existing dashboard.html
# untouched — see index() below for how the branch works). "My Priority
# Actions" replaces Next Actions' old My/Others toggle with a single
# chronological, urgency-grouped list (mine only — Others' Actions moves
# to the new "Waiting on Others" card instead, so there's no toggle left
# to build). At Risk's card is retired entirely — its signal survives only
# as a per-row tag on Priority Actions rows (see _compute_priority_actions
# below) and is no longer a separate list anywhere. Decisions Needed's
# card is ALSO retired from this page — it's now just the "0 decision
# needed" pill in the Today's Focus bar (see dashboard_cs.html) plus the
# "Escalate" button on the Priority Actions card header (reuses the exact
# same Flag to Management modal/route unchanged, see
# _flag_management_modal.html); there is currently NO way to view or
# resolve an ALREADY-raised flag from this new page — flagged-for-CS
# resolution happens for management/admin on their own (unchanged)
# dashboard. Flagged here as a known gap, not an oversight — revisit if
# Ezekiel wants a way to see raised flags from this page too.

def _serialize_owners_list(owner_user):
    """
    get_next_action_owner()['user'] is None | User | list[User] (see
    _is_owner()'s own comment above) — this normalizes all three shapes
    into a plain list of _serialize_person() dicts (0, 1, or several) for
    the Waiting on Others card, which shows one avatar+name chip per
    current owner rather than the CS-lead-then-designers row every other
    card on this page uses (there's no "CS lead vs. designer" split to
    show here — Waiting on Others is specifically about whoever's turn it
    currently is, singular concept, however many people that turns out to
    be).
    """
    if owner_user is None:
        return []
    if isinstance(owner_user, list):
        return [_serialize_person(u) for u in owner_user]
    return [_serialize_person(owner_user)]


def _compute_priority_actions(user):
    """
    "My Priority Actions" (added 16 Jul 2026, CS-only redesign — see the
    big comment above). Replaces Next Actions' old 'mine' bucket: same
    underlying _is_owner()/get_next_action_owner() logic as
    _compute_next_actions(user, 'mine'), but with two differences per
    Ezekiel's spec:

    1. No My/Others toggle — this function ONLY ever returns the viewer's
       own actions (Others' Actions now lives on the separate Waiting on
       Others card, _compute_waiting_on_others() below, so there's nothing
       left to toggle between on this card).
    2. Rows are bucketed into urgency GROUPS instead of one flat list, per
       the mockup ("URGENT" / "TODAY" sections). Ezekiel confirmed the At
       Risk card should fold into this view "via a tag (so at risk tag on
       the row entry)" rather than staying a separate section — this
       function reuses the SAME red/urgent classification
       _compute_next_actions()'s waiting_color already computes elsewhere
       on this page (overdue OR no CS lead OR any requested design team
       unstaffed) to decide BOTH which rows get an at-risk tag AND which
       bucket a row lands in, so "urgent" here can never disagree with
       what a Decisions/Next-Actions row would call red elsewhere.

    Bucket order (JUDGMENT CALL — the mockup only shows "URGENT" and
    "TODAY" in its screenshot, nothing for later/no-deadline projects, so
    the remaining three bands below are a reasonable extrapolation, not
    literal spec):
      'urgent'      — is_overdue OR has_no_cs_lead OR has_missing_designer,
                       REGARDLESS of deadline (a project with no deadline
                       but a missing CS lead/designer is still urgent —
                       matches the mockup's "Shop & Save" row, which shows
                       under URGENT despite "No deadline").
      'today'       — deadline == today, not urgent.
      'this_week'   — deadline within the next 7 days, not urgent/today.
      'later'       — any other real deadline, not urgent.
      'no_deadline' — no deadline at all, not urgent.
    Empty buckets are omitted from the returned list entirely, so
    dashboard_cs.html's loop never renders an empty "LATER" heading with
    nothing under it.

    tags on each row are the SAME {'label':,'variant':} shape
    _compute_at_risk_projects() already uses ('overdue' pulsing red,
    'plain' rose for CS Missing) — deliberately NOT including a flat
    "<Team> Designer Missing" tag here, same "one missing-designer
    indicator per row" rule the At Risk card's own duplicate-tag fix
    established (12-13 Jul 2026, see CLAUDE.md) — the red fallback chip in
    item.designers (rendered via dash_row_people()) already covers that
    fact, so repeating it as a flat tag would reintroduce the exact bug
    that rule exists to prevent.
    """
    today = date.today()
    week_end = today + timedelta(days=7)

    rows = []
    for p in _scoped_projects(user, active_only=True).all():
        owner_info = get_next_action_owner(p)
        if not _is_owner(owner_info['user'], user):
            continue

        deadline = nearest_deadline(p)
        requested_teams = [t.strip() for t in (p.design_teams_requested or '').split(',') if t.strip()]
        designers = _due_row_people(p, requested_teams)
        has_missing_designer = any(not team['users'] for team in designers)
        # 17 Jul 2026, per Ezekiel — a project already at submitted stage
        # (see _SUBMITTED_STAGE_STATUSES) has its design deadline behind
        # it for a reason that isn't "late": the work already left the
        # design team's hands. Its real next action here is correctly
        # still "Follow up with client" (this row exists at all because
        # _is_owner() said it's the CS's own turn) — it just shouldn't
        # ALSO wear a stale Overdue tag / land in the urgent bucket on
        # that basis. has_no_cs_lead/has_missing_designer are unaffected
        # — those are staffing gaps, not deadline pressure, and stay
        # urgent regardless of submission stage.
        is_overdue = bool(deadline) and deadline < today and p.project_status not in _SUBMITTED_STAGE_STATUSES
        has_no_cs_lead = not p.cs_lead_id
        is_urgent = is_overdue or has_no_cs_lead or has_missing_designer

        tags = []
        if is_overdue:
            tags.append({'label': 'Overdue', 'variant': 'overdue'})
        if has_no_cs_lead:
            tags.append({'label': 'CS Missing', 'variant': 'plain'})

        if is_urgent:
            group_key = 'urgent'
        elif deadline == today:
            group_key = 'today'
        elif deadline and today < deadline <= week_end:
            group_key = 'this_week'
        elif deadline:
            group_key = 'later'
        else:
            group_key = 'no_deadline'

        rows.append({
            'project_id': p.id,
            'type': 'project',
            'project_name': p.name,
            'guidance': guidance_for_viewer(owner_info, user),
            'deadline': deadline.isoformat() if deadline else None,
            '_sort_deadline': deadline,
            'cs_lead': _serialize_person(p.cs_lead),
            'designers': designers,
            'tags': tags,
            'group_key': group_key,
        })

    rows.sort(key=lambda r: r['_sort_deadline'] or date.max)
    for r in rows:
        del r['_sort_deadline']

    labels = {
        'urgent': 'Urgent',
        'today': 'Today',
        'this_week': 'This Week',
        'later': 'Later',
        'no_deadline': 'No Deadline',
    }
    grouped = []
    for key in ('urgent', 'today', 'this_week', 'later', 'no_deadline'):
        group_rows = [r for r in rows if r['group_key'] == key]
        if group_rows:
            # 'rows', NOT 'items' — Jinja's `.` accessor tries attribute
            # lookup before dict-key lookup, and a plain dict already has a
            # builtin `.items()` method (the standard dict iteration
            # method). `group.items` in the template would silently resolve
            # to that BOUND METHOD instead of this list, blowing up with
            # "TypeError: 'builtin_function_or_method' object is not
            # iterable" at `{% for item in group.items %}` — caught live via
            # a traceback from dashboard_cs.html line 135. Same footgun
            # would apply to a key named 'keys' or 'values'. `group['items']`
            # (bracket access) would have worked fine — it's specifically
            # Jinja's dot-shorthand that collides with dict builtins.
            grouped.append({'key': key, 'label': labels[key], 'rows': group_rows})
    return grouped


def _compute_waiting_on_others(user):
    """
    "Waiting on Others" (added 16 Jul 2026, CS-only redesign — see the big
    comment above). Replaces Next Actions' old 'others' bucket — same
    underlying _is_owner()/get_next_action_owner() logic as
    _compute_next_actions(user, 'others'), but rendered as a compact
    single-owner list per Ezekiel: "shows projects that are in design
    stage or waiting on client, with the next overall step... It will show
    the owner (example if it's designer show designer name and image, if
    it's on CS, show their name and image) and it will show waiting since
    for each entry."

    'owners' (_serialize_owners_list(), see above) is 0-2 people — almost
    always exactly 1 (whoever's turn it is), but get_next_action_owner()
    can return a list for concept/KV split-designer cases, so this stays
    list-shaped to match rather than silently dropping a second owner.

    'guidance' is the RAW owner_info['guidance'] — deliberately NOT run
    through guidance_for_viewer() (contrast with Priority Actions/Due/Next
    Actions elsewhere on this page, which swap CS-role guidance for "No
    action required" when the VIEWER can't act on it). That swap exists to
    stop a designer from seeing an actionable-looking CS instruction they
    can't do anything about; this card is explicitly informational ("what
    is the other person doing"), not a call to action for the viewer, so
    showing the real next step (e.g. "Follow up with client") is the
    correct read here regardless of the viewer's own role.

    waiting_since_display reuses the same "started_at of the currently
    open ProjectStatusLog row" logic _compute_next_actions() already
    established — see _format_waiting_date().
    """
    results = []
    for p in _scoped_projects(user, active_only=True).all():
        owner_info = get_next_action_owner(p)
        if _is_owner(owner_info['user'], user):
            continue

        deadline = nearest_deadline(p)
        waiting_since = next((sl.started_at for sl in p.status_logs if sl.ended_at is None), None)
        results.append({
            'project_id': p.id,
            'project_name': p.name,
            'guidance': owner_info['guidance'],
            'owners': _serialize_owners_list(owner_info['user']),
            'owner_role': owner_info['role'],
            'deadline': deadline.isoformat() if deadline else None,
            'waiting_since_display': _format_waiting_date(waiting_since),
        })

    results.sort(key=lambda r: r['deadline'] or '9999-12-31')
    return results


def _compute_my_escalated_projects(user):
    """
    "My Escalated Projects" — CS dashboard only (added 17 Jul 2026, Decision
    Flag reply/resolve feature). Every project where THIS specific CS
    personally raised the currently-active DecisionFlag — not just any
    project in their scope that happens to be flagged (a designer or team
    lead on the same project could have raised it instead). Gives a CS a
    place to track their own escalations and reply to whatever management
    has said back, without hunting through project detail pages.

    Deliberately narrower than _compute_decisions() (management's queue,
    every flag in scope regardless of who raised it) — this is "flags I
    personally sent up", so a CS only sees rows they'd actually recognize
    raising. Completely absent from the page (not just empty-stated) when
    this list is empty — see dashboard_cs.html's {% if my_escalated_
    projects %} guard, same "hide entirely, no empty state" treatment
    _compute_priority_actions()'s groups already get for an empty bucket.

    reply_count lets the row show a small "N replies" badge without the
    template needing to know anything about DecisionFlagMessage directly.
    """
    projects = _scoped_projects(user, active_only=True).filter(
        Project.decision_needed.is_(True)
    ).all()

    rows = []
    for p in projects:
        flag = p.active_decision_flag
        if not flag or flag.created_by_id != user.id:
            continue
        rows.append({
            'project_id': p.id,
            'project_name': p.name,
            'note': flag.note,
            'raised_at': flag.created_at.isoformat() if flag.created_at else None,
            'waiting_since_display': _format_waiting_date(flag.created_at),
            'reply_count': len(flag.messages),
        })

    rows.sort(key=lambda r: r['raised_at'] or '')
    return rows


def _compute_my_escalation_history(user):
    """
    "My Escalation History" — CS dashboard only (added 17 Jul 2026). Every
    RESOLVED DecisionFlag this specific CS personally raised, most recently
    resolved first — the closed-out counterpart to My Escalated Projects
    above (which only ever shows the currently OPEN ones). Per Ezekiel:
    "we need to keep that escalation history and give it a spot on the
    dashboard to open a hidden div with those escalations and their
    message history."

    Deliberately queried directly off DecisionFlag rather than through
    _scoped_projects() the way every other row list on this page is built
    — a resolved flag's project may since have moved out of the CS's
    active scope entirely (approved, put on hold, reassigned to a
    different CS), and none of that should make this CS's own record of
    what they once escalated disappear. This is a personal log, not a
    live "what needs my attention" view, so it deliberately doesn't follow
    the same active-scope rule every other card on this page does.

    Rows open the SAME shared Decision Flag modal every other row on this
    page uses (openDecisionFlagModal(), dashboard.js), but pass this
    flag's own id — get_decision_flag()'s flag_id query param (added
    alongside this feature, projects_detail.py) is what makes the modal
    open THIS specific resolved flag instead of whatever's currently
    active on the project (which would be None, or a different, newer
    flag, if the project's been re-escalated since this one closed).

    Capped at the 100 most recently resolved flags — see
    _compute_escalation_history()'s docstring for the same judgment call,
    made in both places for the same reason.
    """
    flags = (
        DecisionFlag.query
        .filter_by(created_by_id=user.id, is_resolved=True)
        .order_by(DecisionFlag.resolved_at.desc())
        .limit(100)
        .all()
    )

    rows = []
    for flag in flags:
        p = flag.project
        if not p:
            continue
        rows.append({
            'project_id': p.id,
            'project_name': p.name,
            'flag_id': flag.id,
            'note': flag.note,
            'raised_at': flag.created_at.isoformat() if flag.created_at else None,
            'resolved_at': flag.resolved_at.isoformat() if flag.resolved_at else None,
            'resolved_display': _format_waiting_date(flag.resolved_at),
            'resolved_by': _serialize_person(flag.resolved_by),
            'resolution_note': flag.resolution_note,
            'reply_count': len(flag.messages),
        })
    return rows


def _compute_escalation_history():
    """
    "Escalation History" — leadership dashboard only (added 17 Jul 2026).
    EVERY resolved DecisionFlag company-wide, most recently resolved
    first — the closed-out counterpart to the Decision Needed Queue above
    (_compute_decisions(scope_user, all_flags=True), which only ever shows
    the currently OPEN ones). Same request as My Escalation History above
    drove this one too; see that function's docstring for the full quote.

    Deliberately takes no `user`/scope argument at all — same "always
    company-wide, not part of the All/Focused toggle" rule Decisions
    Needed/Deadline Clashes/Role Snapshot already follow on this page (see
    the big comment on _compute_risk_overdue() further down for that
    convention) — an escalation's resolution is a company-wide oversight
    record, not something that should shrink to "just my own projects"
    when a manager flips to Focused.

    Capped at the 100 most recently resolved flags — this list only ever
    grows over time, and nothing else on this page shows an unbounded row
    count. A judgment call, not explicit spec — worth revisiting with real
    pagination if 100 ever turns out to be too few in practice.
    """
    flags = (
        DecisionFlag.query
        .filter_by(is_resolved=True)
        .order_by(DecisionFlag.resolved_at.desc())
        .limit(100)
        .all()
    )

    rows = []
    for flag in flags:
        p = flag.project
        if not p:
            continue
        rows.append({
            'project_id': p.id,
            'project_name': p.name,
            'flag_id': flag.id,
            'note': flag.note,
            'raised_by': _serialize_person(flag.created_by),
            'raised_at': flag.created_at.isoformat() if flag.created_at else None,
            'resolved_at': flag.resolved_at.isoformat() if flag.resolved_at else None,
            'resolved_display': _format_waiting_date(flag.resolved_at),
            'resolved_by': _serialize_person(flag.resolved_by),
            'resolution_note': flag.resolution_note,
            'reply_count': len(flag.messages),
        })
    return rows


def _compute_flaggable_projects(user):
    """
    Feeds the project picker inside the Flag to Management modal (see
    dashboard.html + dashboard.js). The modal's spec (from the UI prompt)
    describes a "read-only project name field" — implying the project is
    already known before the modal opens, which is true when the modal is
    launched from a specific project's own page. But the Decisions Needed
    card's "Escalate" shortcut (renamed from "Flag a Project" 16 Jul
    2026 — see decisions.html) is launched from the DASHBOARD, which
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
    _, scope_user, _, _ = _resolve_dashboard_scope(get_actor())
    return jsonify(_compute_clashes_response(scope_user))


# ── Leadership dashboard (management/admin) — 16 Jul 2026 ─────────────────
# Per Ezekiel, sharing a mockup screenshot of a leadership-focused layout
# (WELCOME/Leadership Focus bar/Decision Needed Queue/Risk-Overdue toggle +
# Waiting on Others/Role Snapshot), clarified via five plain-text answers:
# (1) the mockup's small italic-style caption lines ("Greene: separate
# leadership decisions...", "Show what is late or structurally blocked",
# "Clarifies where authority sits", the footer "Greene view: ...", the
# "Visible accountability without surveillance" tagline) are design notes
# ONLY — none of them render on the page, same treatment the CS mockup's
# italic subtitles got. (2) Full replacement of the old management/admin
# dashboard.html (tab-strip/toggle-box layout) — admin gets this too for
# now, since Ezekiel's dedicated admin app/server-health dashboard is a
# separate build for tomorrow ("for now I will see what management
# sees"). (3) The mockup's OWNER column and REQUESTED BY column merge into
# one — there was never a separate "decision owner" concept in the data
# model to begin with (_compute_decisions() below has always had exactly
# one person per flag, decision_raised_by/'raised_by'), so this needed no
# code change, just confirms the existing single column is correct and no
# new OWNER field/UI should be added. (4) Risk/Overdue's green "Start
# project"/"Assign owner" boxes in the mockup are NOT static next-action
# labels — they're real one-click agency: management can reassign a
# project's CS lead or assign a designer directly from this card, each via
# a popup modal matching the app's existing modal style (see
# _flag_management_modal.html). Assign Designer is scoped to "the active
# teams requested for that project" — i.e. only designers on a team the
# project actually asked for, via _missing_designer_teams() below. (5) The
# mockup's top-right "VIEWING AS Shibi [CS]" badge is the EXISTING global
# emulation-badge component (base.html's `{% if is_emulating %}` block,
# unrelated to this dashboard build) — confirmed by design, not rebuilt.
#
# The Decision Needed Queue reuses _compute_decisions(user, all_flags=True)
# UNCHANGED — company-wide, every currently-open flag, matching "My View"'s
# existing all_flags=True behavior (see _resolve_dashboard_scope()) — no
# new compute function needed for that card.

def _compute_risk_overdue(user):
    """
    Leadership dashboard's "Risk / Overdue" toggle box. Three MUTUALLY
    EXCLUSIVE buckets — JUDGMENT CALL, not explicit spec: the mockup showed
    three toggle pills with small, clearly distinct counts ("Overdue 1",
    "At Risk 2", "No Deadline 1"), which only makes sense if a project
    can't land in more than one bucket at once (otherwise the same
    staffing gap could inflate both Overdue's and At Risk's counts for the
    same project). Priority when a project could qualify for more than
    one: overdue beats staffing-gap beats no-deadline — deadline pressure
    is the more urgent signal, so a project that's BOTH overdue AND
    missing a designer shows under Overdue, not At Risk.

      - 'overdue'     — nearest_deadline(project) has passed, ANY amount
                         (not the At Risk CARD's 1-7-day window elsewhere
                         on this page — leadership wants visibility into
                         everything late, not just this week's).
      - 'at_risk'     — not overdue, but missing a CS lead or a requested
                         design team has nobody assigned (same
                         _missing_designer_teams() check At Risk/Next
                         Actions/Clashes already use elsewhere, just
                         consuming the raw team list instead of the
                         rendered label strings).
      - 'no_deadline' — neither of the above, and nearest_deadline is None
                         outright.
    A project matching none of the three (has a future deadline, fully
    staffed) is simply omitted — nothing wrong to report.

    Every row carries has_no_cs_lead / missing_teams so
    dashboard_leadership.html can show a "Reassign CS Lead" / "Assign
    Designer" button per Ezekiel: "Risk overdue let management reassign a
    CS lead or reassign a designer so they have that agency" — Assign
    Designer scoped to missing_teams specifically ("based on the active
    teams requested for that project").

    17 Jul 2026, per Ezekiel: "If a customer is overdue for a C&CM
    project, show that, because right now it shows the project but not
    the customers. Each customer can be it's own entry." — the 'overdue'
    bucket is now CUSTOMER-granular for C&CM projects: one row per
    overdue ProjectCustomer (carrying a customer_name), not one row for
    the whole project. A C&CM project can therefore contribute MULTIPLE
    'overdue' rows (or none). Every customer-level row still also applies
    the submitted-stage exclusion (_customer_is_submitted_stage()) —
    same "waiting on others, not overdue" rule _compute_due() now
    follows. Standard (non-C&CM) projects are unaffected in granularity
    (still one project-level row via nearest_deadline()), just gained the
    equivalent project_status-based submitted-stage exclusion. A C&CM
    project with zero currently-overdue (non-submitted-stage) customers
    NEVER falls back to a project-level 'overdue' row — the customer loop
    is now the ONLY source of 'overdue' bucket membership for C&CM, so
    the bucket can't disagree with itself between two different
    deadline-resolution strategies for the same project.
    """
    today = date.today()
    buckets = {'overdue': [], 'at_risk': [], 'no_deadline': []}

    for p in _scoped_projects(user, active_only=True).all():
        has_no_cs_lead = not p.cs_lead_id
        missing_teams = _missing_designer_teams(p)
        requested_teams = _requested_teams_list(p)
        is_ccm = p.brief_type == 'ccm'

        if is_ccm:
            any_overdue_customer = False
            for pc in p.project_customers:
                if pc.cancelled or pc.status == 'approved':
                    continue
                if _customer_is_submitted_stage(pc):
                    continue
                if pc.design_deadline and pc.design_deadline < today:
                    any_overdue_customer = True
                    tags = [{'label': 'Overdue', 'variant': 'overdue'}]
                    if has_no_cs_lead:
                        tags.append({'label': 'CS Missing', 'variant': 'plain'})
                    buckets['overdue'].append({
                        'project_id': p.id,
                        'name': p.name,
                        'customer_name': pc.customer.name if pc.customer else None,
                        'tags': tags,
                        'deadline': pc.design_deadline.isoformat(),
                        'cs_lead': _serialize_person(p.cs_lead),
                        'designers': _due_row_people(p, requested_teams),
                        'has_no_cs_lead': has_no_cs_lead,
                        'missing_teams': missing_teams,
                    })
            if any_overdue_customer:
                continue
            # No overdue (non-submitted-stage) customer — fall through to
            # at_risk/no_deadline only; 'overdue' is deliberately
            # unreachable here (see docstring above).
            deadline = nearest_deadline(p)
            if has_no_cs_lead or missing_teams:
                bucket_key = 'at_risk'
            elif deadline is None:
                bucket_key = 'no_deadline'
            else:
                continue
        else:
            deadline = nearest_deadline(p)
            is_submitted = p.project_status in _SUBMITTED_STAGE_STATUSES
            if deadline and deadline < today and not is_submitted:
                bucket_key = 'overdue'
            elif has_no_cs_lead or missing_teams:
                bucket_key = 'at_risk'
            elif deadline is None:
                bucket_key = 'no_deadline'
            else:
                continue

        tags = []
        if bucket_key == 'overdue':
            tags.append({'label': 'Overdue', 'variant': 'overdue'})
        if has_no_cs_lead:
            tags.append({'label': 'CS Missing', 'variant': 'plain'})

        buckets[bucket_key].append({
            'project_id': p.id,
            'name': p.name,
            'customer_name': None,
            'tags': tags,
            'deadline': deadline.isoformat() if deadline else None,
            'cs_lead': _serialize_person(p.cs_lead),
            'designers': _due_row_people(p, requested_teams),
            'has_no_cs_lead': has_no_cs_lead,
            'missing_teams': missing_teams,
        })

    for key in buckets:
        buckets[key].sort(key=lambda r: r['deadline'] or '9999-12-31')

    return buckets


def _compute_leadership_waiting_on_others(user):
    """
    Leadership dashboard's "Waiting on Others" card — company-wide (unlike
    the CS dashboard's card of the same name, which is scoped to that one
    CS's own projects). Per Ezekiel: "shows all projects that are waiting
    on people who are not the CS lead, the status and a button to follow
    up if it's a decision, or assign if a designer hasn't assigned
    themselves."

    Two DISJOINT row types, checked in this order per project (a project
    can only ever produce one row here, same "don't double-count" reasoning
    _compute_risk_overdue() uses):
      - 'assign'    — a requested design team has nobody assigned
                       (_missing_designer_teams()) — "Waiting for: Designer
                       assignment", Assign button.
      - 'follow_up' — project_status == 'submitted_to_client' (the one
                       status in the current get_next_action_owner()
                       status_map whose guidance is literally "Follow up
                       with client" — see dashboard_logic.py) — "Waiting
                       for: Client confirmation", Follow up button.
    Every other project (internal work in progress, nothing externally
    blocked) is simply not shown — this card is specifically about
    external/staffing blockers, not a general "what's everyone doing" feed
    (that's Role Snapshot, below).

    age_days / age_display: days since the CURRENTLY OPEN ProjectStatusLog
    row started (same "started_at of the open status-log row" signal
    _format_waiting_date()/Next Actions' waiting_since already use
    elsewhere), rendered as "Today"/"1 day"/"N days" rather than reusing
    _format_waiting_date()'s "13 Jul" format — the mockup shows relative
    age ("Age: Today", "Age: 1 day"), not a calendar date, for this card
    specifically.
    """
    results = []
    for p in _scoped_projects(user, active_only=True).all():
        missing_teams = _missing_designer_teams(p)
        if missing_teams:
            row_type = 'assign'
            waiting_for = 'Designer assignment'
        elif p.project_status == 'submitted_to_client':
            row_type = 'follow_up'
            waiting_for = 'Client confirmation'
        else:
            continue

        open_log = next((sl for sl in p.status_logs if sl.ended_at is None), None)
        if open_log and open_log.started_at:
            age_days = (datetime.utcnow() - open_log.started_at).days
            age_display = 'Today' if age_days == 0 else ('1 day' if age_days == 1 else f'{age_days} days')
        else:
            age_days = None
            age_display = '—'

        results.append({
            'project_id': p.id,
            'project_name': p.name,
            'row_type': row_type,
            'waiting_for': waiting_for,
            'age_display': age_display,
            'missing_teams': missing_teams,
        })

    results.sort(key=lambda r: r['project_name'])
    return results


# Priority order for Role Snapshot's single secondary stat per person —
# JUDGMENT CALL, flagged rather than guessed at silently. The mockup shows
# a DIFFERENT stat category per person (Kulsoom: "2 next actions", Mohsin:
# "1 pending", Prim: "3 waiting", Rehan: "1 clash", Waseem: "clear") with
# no explanation of why each person shows the one they do — read as "show
# whichever single fact is most worth a leader's attention", so this list
# is that priority, most urgent first. A person matching more than one
# category only ever shows the highest-priority one (never stacks two
# stats on a Role Snapshot tile — there's no room, and the mockup only
# ever shows one per person).
#   1. 'clash'   — involved in a deadline clash (compute_clashes()) — a
#                  scheduling conflict is the most concretely urgent thing
#                  that can be true about a person's workload.
#   2. 'actions' — projects where it's currently THIS person's turn to act
#                  (get_next_action_owner()/_is_owner()) — work is sitting
#                  waiting on them specifically.
#   3. 'pending' — CS-only: their projects currently sitting in
#                  'submitted_to_client' (client-approval limbo) — not
#                  blocking THEM, but worth a leader knowing it's pending.
#   4. 'waiting' — their projects where it's someone ELSE'S turn (the
#                  mirror image of 'actions') — lowest-urgency non-clear
#                  state, included so "clear" is reserved for genuinely
#                  nothing outstanding.
#   5. 'clear'   — none of the above — fallback.
_ROLE_SNAPSHOT_ROLES = ('cs', 'designer', 'team_lead')


def _compute_role_snapshot():
    """
    Leadership dashboard's "Role Snapshot" row — one tile per CS/designer/
    team_lead user (management/admin excluded — this card is about the
    people doing project work, not about the viewer's own peers), each
    showing their active project count plus ONE priority-ordered secondary
    stat (see the big comment above _ROLE_SNAPSHOT_ROLES) and a status dot
    colour (red for 'clash'/'actions', amber for 'pending'/'waiting', green
    for 'clear' — same red/amber/green story every other urgency signal on
    this page tells).

    Always company-wide (User.query, not _scoped_projects(management_user)
    — this card is inherently about OTHER people's workloads, there's no
    "viewer's own scope" to narrow it by).

    Segregated 16 Jul 2026, same-day follow-up — per Ezekiel: "Role
    snapshot needs to be segregrated. Client servicing row. Designer Row
    (split into the 3 teams, 2d, 3d and technical)." Return shape changed
    from a flat list to a dict: `cs` (all CS tiles), `designers_by_team`
    (dict keyed '3D'/'2D'/'Technical', reusing the exact team name strings
    _TEAM_MISSING_LABELS already uses elsewhere on this page — one source
    of truth for team naming), and `designers_unassigned` (defensive
    bucket for a designer/team_lead with no `.team` set — shouldn't
    normally happen, but better than silently dropping them). team_lead
    users are grouped into their own team's bucket alongside designers
    (not a 4th top-level group) — per Ezekiel's literal phrasing this is a
    "Designer Row" split by team, and a team lead IS on one of the three
    design teams, same as any designer.
    """
    all_projects = Project.query.filter(Project.project_status != 'draft', Project.project_status != 'approved').all()
    clashes = compute_clashes(all_projects)
    clash_designer_ids = set()
    for c in clashes['by_deliverable']:
        clash_designer_ids.add(c['designer_id'])
    for c in clashes['by_project']:
        clash_designer_ids.add(c['designer_id'])

    tiles_cs = []
    tiles_by_team = {'3D': [], '2D': [], 'Technical': []}
    tiles_unassigned = []

    for u in User.query.filter(User.role.in_(_ROLE_SNAPSHOT_ROLES)).order_by(User.name.asc()).all():
        scoped = _scoped_projects(u, active_only=True).all()
        active_count = len(scoped)

        if u.id in clash_designer_ids:
            stat_key, stat_count = 'clash', sum(
                1 for c in clashes['by_deliverable'] if c['designer_id'] == u.id
            ) + sum(
                1 for c in clashes['by_project'] if c['designer_id'] == u.id
            )
        else:
            my_actions = sum(1 for p in scoped if _is_owner(get_next_action_owner(p)['user'], u))
            if my_actions:
                stat_key, stat_count = 'actions', my_actions
            elif u.role == 'cs' and any(p.project_status == 'submitted_to_client' for p in scoped):
                stat_key, stat_count = 'pending', sum(1 for p in scoped if p.project_status == 'submitted_to_client')
            else:
                waiting = sum(1 for p in scoped if not _is_owner(get_next_action_owner(p)['user'], u))
                stat_key, stat_count = ('waiting', waiting) if waiting else ('clear', 0)

        stat_labels = {
            'clash': 'clash' if stat_count == 1 else 'clashes',
            'actions': 'next action' if stat_count == 1 else 'next actions',
            'pending': 'pending',
            'waiting': 'waiting',
            'clear': 'clear',
        }
        dot_color = {
            'clash': 'red', 'actions': 'red', 'pending': 'amber', 'waiting': 'amber', 'clear': 'green',
        }[stat_key]

        tile = {
            'user_id': u.id,
            'name': u.name,
            'avatar_filename': u.avatar_filename,
            'active_count': active_count,
            'stat_key': stat_key,
            'stat_count': stat_count,
            'stat_label': stat_labels[stat_key],
            'dot_color': dot_color,
            # Added 16 Jul 2026, per Ezekiel: the CS/Designer toggle tiles
            # "need to be clickable, that shows a hidden div below that
            # shows the details of the info card row by row." Reuses the
            # same plain project-list row shape (name/deadline/status) the
            # Your Active / Pending Approval / Total Active stat cards
            # already show via _stat_project_rows() — `scoped` here is that
            # exact same _scoped_projects(u, active_only=True) list, just
            # not yet serialized. Embedded into the page as a JSON blob
            # (see dashboard_leadership.html) rather than fetched via a new
            # API route, since this data is already fully computed on page
            # load for the count above — no reason to round-trip for it.
            'rows': _stat_project_rows(scoped),
        }

        if u.role == 'cs':
            tiles_cs.append(tile)
        elif u.team in tiles_by_team:
            tiles_by_team[u.team].append(tile)
        else:
            tiles_unassigned.append(tile)

    return {
        'cs': tiles_cs,
        'designers_by_team': tiles_by_team,
        'designers_unassigned': tiles_unassigned,
    }


def _compute_leadership_focus(user, decisions_count, risk_overdue):
    """
    Leadership Focus bar's 5 pills. Reuses counts already computed
    elsewhere in index() (decisions_count from _compute_decisions(),
    risk_overdue's own bucket lengths) rather than re-querying — the bar
    is purely a summary of data every other card on this page already
    fetched.
    """
    clashes = compute_clashes(_scoped_projects(user, active_only=True).all())
    clash_count = len(clashes['by_project']) + len(clashes['by_deliverable'])
    waiting_count = len(_compute_leadership_waiting_on_others(user))

    return {
        'decisions_open': decisions_count,
        'overdue': len(risk_overdue['overdue']),
        'at_risk': len(risk_overdue['at_risk']),
        'clashes': clash_count,
        'waiting_on_others': waiting_count,
    }


@dashboard_bp.route('/api/risk-overdue')
@login_required
def api_risk_overdue():
    _, scope_user, _, _ = _resolve_dashboard_scope(get_actor())
    return jsonify(_compute_risk_overdue(scope_user))


# ── Leadership dashboard: All/Focused toggle (added 17 Jul 2026) ─────────
#
# Per Ezekiel: management/admin can flip between "All" (company-wide) and
# "Focused" (only projects they're personally CS lead/secondary CS on).
# This is a no-reload AJAX toggle (Ezekiel's explicit choice) — the client
# re-fetches each affected card with an explicit ?scope=all|my param. All
# three of these thin routes reuse _resolve_dashboard_scope() exactly like
# /api/risk-overdue and /api/due already do — 'all'/'my' were both already
# fully working scope_mode values (the old view-switcher's 'my' mode never
# went away, just lost its UI when that switcher was removed 16 Jul 2026),
# so no changes were needed to _resolve_dashboard_scope() itself, only new
# thin JSON wrappers around compute functions that already accept a user
# param. Decisions Needed / Deadline Clashes / Role Snapshot deliberately
# have NO equivalent route here — per Ezekiel's explicit answer, those
# three stay company-wide regardless of this toggle, so the client-side
# code driving this toggle (dashboard.js) never touches their existing
# fetch paths at all. See dashboard.js's applyLeadershipFocusScope() for
# the full client-side writeup.
@dashboard_bp.route('/api/active-projects')
@login_required
def api_active_projects():
    _, scope_user, _, _ = _resolve_dashboard_scope(get_actor())
    return jsonify(_compute_your_active_projects(scope_user))


@dashboard_bp.route('/api/pending-approval-projects')
@login_required
def api_pending_approval_projects():
    _, scope_user, _, _ = _resolve_dashboard_scope(get_actor())
    return jsonify(_compute_pending_approval_projects(scope_user))


@dashboard_bp.route('/api/waiting-on-others')
@login_required
def api_waiting_on_others():
    # Leadership-only, same as /api/risk-overdue just above (the CS
    # dashboard's OWN Waiting on Others card, _compute_waiting_on_others(),
    # has no AJAX route at all — it's never needed live re-fetching before
    # now). Flat name despite being leadership-specific matches the
    # existing /api/risk-overdue convention.
    _, scope_user, _, _ = _resolve_dashboard_scope(get_actor())
    return jsonify(_compute_leadership_waiting_on_others(scope_user))


# Added 17 Jul 2026 — per Ezekiel: "Resolved escalations dont auto populate
# into the resolved escalations section, it requires a refresh. Make sure
# everything across all dashboard types is live." Root cause turned out to
# be TWO layers: (1) DecisionFlag/DecisionFlagMessage were never in
# live_events.py's _PROJECT_ID_GETTERS, so no NOTIFY fired at all for any
# decision-flag action (fixed there, same day); (2) even once the doorbell
# rings, nothing in dashboard.js's refreshDashboardFromSSE() actually
# re-fetched these three lists — they were server-rendered once and never
# touched again. These three routes are what that refresh now calls.
@dashboard_bp.route('/api/escalated-projects')
@login_required
def api_escalated_projects():
    # CS dashboard's "My Escalated Projects" card. Same shape as every
    # other /api/* route above.
    _, scope_user, _, _ = _resolve_dashboard_scope(get_actor())
    return jsonify(_compute_my_escalated_projects(scope_user))


@dashboard_bp.route('/api/my-escalation-history')
@login_required
def api_my_escalation_history():
    # CS dashboard only — "My Escalation History" (this CS's own resolved
    # flags). Company-wide equivalent is /api/escalation-history below, a
    # DIFFERENT underlying compute function, not just a scope difference.
    _, scope_user, _, _ = _resolve_dashboard_scope(get_actor())
    return jsonify(_compute_my_escalation_history(scope_user))


@dashboard_bp.route('/api/escalation-history')
@login_required
def api_escalation_history():
    # Leadership dashboard only. _compute_escalation_history() takes no
    # user/scope argument at all — always company-wide, same "not part of
    # the All/Focused toggle" rule Decisions/Clashes/Role Snapshot already
    # follow (see the big comment on _compute_risk_overdue()) — so there's
    # no scope to resolve here.
    return jsonify(_compute_escalation_history())


# Added 18 Jul 2026 — real perf fix, not a new feature. build_time_tracking_
# rows() used to be called unconditionally in index() on EVERY admin/
# management dashboard page load, regardless of whether the Average
# Project Time tab was ever opened — a full company-wide scan (every
# non-draft project, then EACH one's project_deliverables relationship,
# then EACH deliverable's status_logs relationship, plus a business-hours
# calculation per project and per deliverable) that was the dominant cost
# behind a 3+ second dashboard load Ezekiel reported (screenshot showed the
# main HTML request alone taking 3.27s). Moved here so it only runs when a
# user actually clicks the tab — see stat_avg_time.html/dashboard.js for
# the fetch-on-first-open wiring. Returns a rendered HTML fragment (not
# JSON) — the row markup is non-trivial (nested project/deliverable/
# status-chip structure with <details> breakdowns), so reusing the exact
# same Jinja partial server-side avoids duplicating that structure in JS.
@dashboard_bp.route('/api/time-tracking-rows')
@login_required
def api_time_tracking_rows():
    actor = get_actor()
    if actor.role not in ('admin', 'management'):
        abort(403)
    from app.routes.time_tracking import build_time_tracking_rows
    return render_template('dashboard/cards/_stat_avg_time_rows.html', time_tracking_rows=build_time_tracking_rows())


# The deep-dive zone (Projects/Deliverables tabs at the bottom of the
# dashboard — _is_at_risk(), _compute_deep_dive_projects(),
# _compute_deep_dive_deliverables(), and their /api/deep-dive/* routes)
# was REMOVED 13 Jul 2026, per Ezekiel: "remove the side by side view on
# the bottom of the dashboard page, remove that section entirely. the
# bottom of the page should only be the expandable section." See
# CLAUDE.md for the full removal writeup and what's shared vs. exclusive
# (the At Risk CARD's _compute_at_risk_projects() is a different,
# unrelated staffing-gap/overdue check that is NOT part of this removal —
# see its own docstring). Check git history around 13 Jul 2026 if this
# ever needs resurrecting.


# ── Designer / Team Lead dashboard (16 Jul 2026) ─────────────────────────
# Per Ezekiel: "Let's move on to the designer dashboard, the final one.
# This applies to team_lead and designer roles only." Full replacement of
# dashboard.html for layout_role in ('designer', 'team_lead') — same "own
# dedicated layout" precedent dashboard_cs.html/dashboard_leadership.html
# already established for their roles. See index()'s designer/team_lead
# branch (above) for the render_template() call and dashboard_designer.html
# for the template.
#
# A reference mockup ("Designer landing view", Christine) was shared
# alongside the spec, explicitly for "arrangement inspiration" only — the
# written spec (quoted in full in CLAUDE.md) is authoritative wherever the
# two disagree.

def _designer_row_classification(p, user):
    """
    Shared per-project classification both _compute_designer_work_queue()
    and _compute_designer_metrics() need — one source of truth so the
    Blocked bucket's membership can never drift between "what shows in My
    Work Queue" and "what the Blocked counter on Metrics Summary counts",
    the same kind of drift the At Risk card's 13 Jul 2026 duplicate-tag
    bug came from (see CLAUDE.md).

    'missing_info' (blocked reason 2, "a brief is missing information") is
    a JUDGMENT CALL, flagged here and in CLAUDE.md — this codebase has
    never formally defined that phrase anywhere else. Reused the clearest
    gap this app already tracks: nearest_deadline(p) is None (no deadline
    set at all) — same signal the leadership dashboard's own "No Deadline"
    bucket already treats as notable, rather than inventing a new,
    undefined concept from scratch.

    'blocked_2days' (blocked reason 1) — per Ezekiel: "waiting on CS for
    more than 2 days." Reuses the exact same "started_at of the currently
    open ProjectStatusLog row" signal _compute_waiting_on_others() and the
    Decisions/Next-Actions waiting tags already use elsewhere on this page.
    """
    owner_info = get_next_action_owner(p)
    is_my_turn = _is_owner(owner_info['user'], user)
    deadline = nearest_deadline(p)
    waiting_since = next((sl.started_at for sl in p.status_logs if sl.ended_at is None), None)
    waiting_days = (datetime.utcnow() - waiting_since).days if waiting_since else 0
    blocked_2days = (not is_my_turn) and owner_info['role'] == 'cs' and waiting_days >= 2
    missing_info = deadline is None

    return {
        'owner_info': owner_info,
        'is_my_turn': is_my_turn,
        'deadline': deadline,
        'blocked_2days': blocked_2days,
        'missing_info': missing_info,
        'is_blocked': blocked_2days or missing_info,
    }


def _designer_relevant_entries(user):
    """
    17 Jul 2026, per Ezekiel: "the designer dashboard should be
    deliverable based, not project based. So if a customer or deliverable
    is due that day, all assigned people within that customer or
    deliverable should have that on their dashboard as due today. same
    applies to this week, overdue etc." Replaces the old project-level
    ProjectDesigner scope (_scoped_projects()) as My Work Queue's
    scoping unit — querying DeliverableAssignment.designer_id == user.id
    directly (the FINE-GRAINED per-deliverable assignment table, distinct
    from ProjectDesigner's project-level "lead designer for team X") is
    what makes "all assigned people within that deliverable see it, and
    ONLY them" true automatically: two designers assigned to DIFFERENT
    deliverables on the SAME project each independently get their own
    query result, so neither sees the other's deliverable/customer.

    Returns one dict per relevant deliverable/customer (non-draft,
    non-approved project only, mirroring _scoped_projects()'s own
    draft/approved exclusion):
      {'project': Project, 'type': 'deliverable'|'customer',
       'entry_name': str, 'deadline': date|None,
       'is_submitted_stage': bool}
    entry_name is JUST the deliverable/customer's own name (e.g. "Hero
    Banner" or "Mars KSA") — the row macro pairs it with the parent
    project's name itself, same title-inversion pattern dash_due_row()
    already uses ("Hero Banner — Acme Rebrand").

    A C&CM deliverable (Deliverable.project_customer_id is set) collapses
    to ONE row per CUSTOMER, not per deliverable underneath it — same
    "one row per pending customer" granularity _compute_due() already
    uses for C&CM — so a designer assigned to 2+ deliverables under the
    same customer sees that customer once, not twice. deadline for a
    customer row is the CUSTOMER's own design_deadline (the POSM
    submission deadline), not any individual deliverable's.
    """
    assignments = (DeliverableAssignment.query
                   .join(Deliverable, DeliverableAssignment.deliverable_id == Deliverable.id)
                   .join(Project, Deliverable.project_id == Project.id)
                   .filter(DeliverableAssignment.designer_id == user.id)
                   .filter(Project.project_status.notin_(['draft', 'approved']))
                   .all())

    entries = {}  # dedupe key -> entry dict
    for a in assignments:
        d = a.deliverable
        p = d.project
        if d.project_customer_id:
            pc = d.project_customer
            if pc is None or pc.cancelled or pc.status == 'approved':
                continue
            key = ('customer', pc.id)
            if key in entries:
                continue
            entries[key] = {
                'project': p,
                'type': 'customer',
                'entry_name': pc.customer.name if pc.customer else p.name,
                'deadline': pc.design_deadline,
                'is_submitted_stage': _customer_is_submitted_stage(pc),
            }
        else:
            key = ('deliverable', d.id)
            if key in entries:
                continue
            entries[key] = {
                'project': p,
                'type': 'deliverable',
                'entry_name': d.name,
                'deadline': d.design_deadline,
                'is_submitted_stage': d.status in _SUBMITTED_STAGE_STATUSES,
            }

    return list(entries.values())


def _compute_designer_work_queue(user):
    """
    "My Work Queue" — Due Today / This Week / Blocked, per Ezekiel's full
    spec (see CLAUDE.md for the verbatim message). 17 Jul 2026: reworked
    from one row per PROJECT to one row per DELIVERABLE/CUSTOMER — see
    _designer_relevant_entries() — per Ezekiel's follow-up: "the designer
    dashboard should be deliverable based, not project based."

    Two things stay PROJECT-level by necessity, flagged as a deliberate
    scoping decision rather than an oversight: is_my_turn/blocked_2days
    (get_next_action_owner() answers "whose turn for the WHOLE project",
    not per-deliverable — this codebase has no per-deliverable ownership
    concept to draw on) and Project.revision_count (there is no
    per-deliverable revision counter). Every deliverable/customer entry
    under the same project therefore shares that project's single
    is_my_turn/blocked_2days/revision_count answer, while its OWN
    deadline and submitted-stage status are fully entry-specific.

    Bucketing (mutually exclusive, same "no double-counting" rule the
    leadership dashboard's Risk/Overdue buckets follow):
      'blocked'   — waiting on CS 2+ days for this entry's project, OR
                    this SPECIFIC entry has no deadline set
                    (missing_info, JUDGMENT CALL — see
                    _designer_row_classification()'s docstring for the
                    same reasoning, now applied per-entry instead of
                    per-project) — but NEVER an entry already at
                    submitted stage (that's Waiting on Others' job, not
                    Blocked's — matches _compute_due()'s own submitted-
                    stage exclusion, 17 Jul 2026).
      'due_today' — deadline == today, not blocked, not submitted stage.
      'this_week' — deadline <= week_end (JUDGMENT CALL, widened 17 Jul
                    2026 to ALSO include anything already overdue —
                    "same applies to this week, overdue etc" — an
                    overdue-but-still-my-turn entry no longer silently
                    vanishes; it lands in This Week tagged Overdue
                    instead of a dedicated Overdue bucket, since there's
                    no separate Overdue toggle button on this card),
                    not blocked, not submitted stage.
    An entry at submitted stage never lands in ANY of the three buckets —
    per Ezekiel: "these are just visible in waiting on others only."

    Each row carries a 'tags' list ({'label':,'variant':} — same shape
    every other card's tags use) and a 'next_action' string:
      - Blocked: 'Waiting on CS 2+ Days' / 'Missing Brief Info' (red,
        either or both can apply at once), next_action = 'Flag project to
        CS Lead' when missing_info (opens the inline flag modal — see
        dashboard_designer.html) else 'Ping CS Owner'.
      - Due Today/This Week, my turn: 'INITIAL' or 'REVISION <n>'
        (Project.revision_count) plus an additional red 'Overdue' tag
        when this entry's own deadline has passed, next_action = 'Submit
        Initial Submission' / 'Submit Revision <n>'.
      - Due Today/This Week, CS's turn: 'Waiting on CS' (amber),
        next_action = 'Ping CS Owner' — per Ezekiel: "If something is
        waiting on CS action, then add that as a yellow tag."
    """
    today = date.today()
    week_end = today + timedelta(days=7)
    buckets = {'due_today': [], 'this_week': [], 'blocked': []}

    # Cache project-level classification per project id — several
    # deliverables/customers can belong to the same project, and
    # is_my_turn/blocked_2days/revision_count are identical for all of
    # them (see docstring above), so there's no reason to recompute
    # get_next_action_owner() once per entry.
    project_classification = {}

    for entry in _designer_relevant_entries(user):
        p = entry['project']
        if p.id not in project_classification:
            project_classification[p.id] = _designer_row_classification(p, user)
        c = project_classification[p.id]
        cs_lead = _serialize_person(p.cs_lead)
        deadline = entry['deadline']

        if entry['is_submitted_stage']:
            continue

        entry_missing_info = deadline is None
        is_blocked = c['blocked_2days'] or entry_missing_info
        if is_blocked:
            tags = []
            if c['blocked_2days']:
                tags.append({'label': 'Waiting on CS 2+ Days', 'variant': 'red'})
            if entry_missing_info:
                tags.append({'label': 'Missing Brief Info', 'variant': 'red'})
            buckets['blocked'].append({
                'project_id': p.id,
                'entry_type': entry['type'],
                'entry_name': entry['entry_name'],
                'project_name': p.name,
                'client_name': p.client or '',
                # Only actually None when THIS entry has no deadline set
                # (entry_missing_info) — a row blocked purely on
                # blocked_2days (waiting on CS) still has a real deadline
                # and should keep showing it, not fall back to "No
                # Deadline" text. Fixed same-pass — the first version of
                # this rework hardcoded None for every blocked row
                # regardless of reason, a real regression from the old
                # project-level behaviour (which only nulled it when
                # missing_info was the actual reason).
                'deadline': deadline.isoformat() if deadline else None,
                'cs_lead': cs_lead,
                'tags': tags,
                'next_action': 'Flag project to CS Lead' if entry_missing_info else 'Ping CS Owner',
                'show_flag_button': entry_missing_info,
            })
            continue

        if deadline > week_end:
            continue

        is_overdue = deadline < today
        if c['is_my_turn']:
            revision_count = p.revision_count or 0
            if revision_count > 0:
                tags = [{'label': f'REVISION {revision_count}', 'variant': 'amber'}]
                next_action = f'Submit Revision {revision_count}'
            else:
                tags = [{'label': 'INITIAL', 'variant': 'initial'}]
                next_action = 'Submit Initial Submission'
        else:
            tags = [{'label': 'Waiting on CS', 'variant': 'amber'}]
            next_action = 'Ping CS Owner'
        if is_overdue:
            tags.append({'label': 'Overdue', 'variant': 'overdue'})

        row = {
            'project_id': p.id,
            'entry_type': entry['type'],
            'entry_name': entry['entry_name'],
            'project_name': p.name,
            'client_name': p.client or '',
            'deadline': deadline.isoformat(),
            'cs_lead': cs_lead,
            'tags': tags,
            'next_action': next_action,
            'show_flag_button': False,
        }

        if deadline == today:
            buckets['due_today'].append(row)
        buckets['this_week'].append(row)

    for key in buckets:
        buckets[key].sort(key=lambda r: r['deadline'] or '9999-12-31')

    return buckets


def _compute_designer_week_load(user):
    """
    "This Week Load" — Mon-Fri counts of deadlines landing on each day,
    colour-coded per Ezekiel: "0-1 green, 2-3 yellow, 4+ red." Uses the
    CURRENT calendar week (Monday through Friday), not a rolling 5-day
    window starting from today — a JUDGMENT CALL, matching the mockup's
    fixed Mon-Fri layout over a "today + next 4 workdays" reading.

    17 Jul 2026: reworked from one count per PROJECT (nearest_deadline())
    to one count per DELIVERABLE/CUSTOMER this designer is personally
    assigned to (_designer_relevant_entries()) — same "deliverable based,
    not project based" rework as _compute_designer_work_queue(), applied
    here too for consistency: a designer with 3 deliverables due Tuesday
    across 2 different projects should see "3" on Tuesday, not have that
    collapse to fewer project-level counts. Submitted-stage entries are
    excluded here too, same reasoning as everywhere else on this page —
    a deadline that's already out of the design team's hands shouldn't
    inflate this workload count.
    """
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    days = [monday + timedelta(days=i) for i in range(5)]
    counts = {d: 0 for d in days}

    for entry in _designer_relevant_entries(user):
        if entry['is_submitted_stage']:
            continue
        deadline = entry['deadline']
        if deadline in counts:
            counts[deadline] += 1

    def color_for(n):
        if n <= 1:
            return 'green'
        if n <= 3:
            return 'amber'
        return 'red'

    return [{
        'label': d.strftime('%a'),
        'date': d.strftime('%d %b'),
        'is_today': d == today,
        'count': counts[d],
        'color': color_for(counts[d]),
    } for d in days]


def _compute_designer_metrics(user):
    """
    "Metrics Summary" — Assigned / Submitted / Blocked / Revisions
    counters, each with an expandable row list (per Ezekiel: "counters
    that can be clicked to expand below and show the relevant details to
    click on those projects"). Reuses _stat_project_rows() (the same
    plain project-list serializer Your Active/Pending Approval already
    use) for Assigned/Submitted/Revisions; Blocked reuses
    _compute_designer_work_queue()'s own 'blocked' bucket directly rather
    than re-deriving the same classification a second time (see
    _designer_row_classification()'s docstring on why that would risk
    drift) — rendered via dash_designer_queue_row(), not
    dash_stat_project_row(), since those rows already carry the richer
    tag/CS-lead/next-action detail and there's no reason to throw that
    away just because this panel is reached via a different counter.

    'submitted' JUDGMENT CALL: project_status in ('submitted',
    'internal_review', 'submitted_to_client') — "work has been handed off
    and is awaiting someone else," the closest reading of "submitted
    projects" this app's status vocabulary supports.
    'revisions' JUDGMENT CALL: Project.revision_count > 0, regardless of
    whose turn it currently is (a project that's ever been through a
    revision cycle, not just ones currently awaiting a resubmit).

    17 Jul 2026: Assigned/Submitted/Revisions are DELIBERATELY still
    project-level (_scoped_projects(), via the project-level ProjectDesigner
    assignment) even though My Work Queue itself moved to deliverable/
    customer granularity (_designer_relevant_entries(), via
    DeliverableAssignment) — Ezekiel's "deliverable based, not project
    based" request was specifically about the due-today/this-week/overdue
    concept, and "how many projects am I the lead designer on" is a
    different, still-legitimately-project-level question. Blocked is the
    one exception: it's inherited AS-IS from
    _compute_designer_work_queue()['blocked'], which IS now
    deliverable/customer-granular, same as always (avoiding re-deriving
    the same classification a second time — see this function's own
    intro comment above).
    """
    assigned = _scoped_projects(user, active_only=True).all()
    submitted = [p for p in assigned if p.project_status in ('submitted', 'internal_review', 'submitted_to_client')]
    revisions = [p for p in assigned if (p.revision_count or 0) > 0]
    blocked_rows = _compute_designer_work_queue(user)['blocked']

    return {
        'assigned': {'count': len(assigned), 'rows': _stat_project_rows(assigned)},
        'submitted': {'count': len(submitted), 'rows': _stat_project_rows(submitted)},
        'blocked': {'count': len(blocked_rows), 'rows': blocked_rows},
        'revisions': {'count': len(revisions), 'rows': _stat_project_rows(revisions)},
    }


def _compute_designer_focus(work_queue, metrics):
    """
    Designer Focus bar's pills — derived from already-computed work_queue/
    metrics dicts (same "reuse what index() already fetched, don't
    re-query" rule _compute_leadership_focus() follows) rather than a
    fixed field set copied verbatim from the CS/management bars — this
    role's most relevant at-a-glance numbers are different from either of
    those (no "decisions"/"clashes" concept for an individual designer's
    own queue). JUDGMENT CALL: the exact pill set wasn't specified beyond
    "similar to the CS and management versions" (i.e. reuse
    .dash-focus-bar's styling, not necessarily its exact field set).
    """
    return {
        'due_today': len(work_queue['due_today']),
        'this_week': len(work_queue['this_week']),
        'blocked': len(work_queue['blocked']),
        'submitted': metrics['submitted']['count'],
        'revisions': metrics['revisions']['count'],
    }
