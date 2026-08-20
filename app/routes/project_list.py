#   app/routes/project_list.py
#   
#   Rewrite of the projects page. Replaces main.projects() and its three role branched render targets
#   All now within one template that adapts to the viewing user's role, per app architecture

from datetime import date
from flask import Blueprint, render_template, session, request, jsonify, url_for, redirect
from flask_login import login_required, current_user
from sqlalchemy import nullslast
from app import db
from app.models import Project, ProjectSecondaryCS, ProjectDesigner, Deliverable, User as UserModel, Client, UserTableLayout, ProjectCustomer, DesignType, ProjectTableView, ProjectStatusLog
from app.status_vocabulary import derive_deliverable_status, derive_project_status, derive_customer_pipeline_status

project_list_bp = Blueprint('project_list', __name__, url_prefix='/projects-new')

def _serialize_person(u):
    """Same architecture as dashboard.py's _serialize_person"""
    if not u:
        return None
    return {'id': u.id, 'name': u.name, 'avatar_filename': u.avatar_filename}

def _effective_user():
    """Same emulation-aware-actor lookup every other route in this app uses"""
    emulating_id = session.get('emulating_user_id')
    if emulating_id and current_user.role == 'admin':
        return UserModel.query.get(emulating_id)
    return current_user

def _next_deadline_for(deliverable_query):
    """
    Given a Deliverable query already scoped to "this project" or "this
    customer," finds the single most urgent deadline: the earliest
    design_deadline among deliverables that aren't Approved yet.

    Approved deliverables are excluded because once a deliverable is
    Approved there's nothing left to be "next" about — it's done.
    Everything else (in_progress, submitted, revision states, etc.) still
    has a live deadline that matters.

    Deliberately does NOT filter out deadlines that have already passed —
    an overdue deliverable is still the most urgent thing to show, not
    something to quietly drop once its date is behind us.
    """
    d = (
        deliverable_query
        .filter(Deliverable.status != 'approved')
        .order_by(nullslast(Deliverable.design_deadline), nullslast(Deliverable.design_deadline_time))
        .first()
    )
    if d is None or d.design_deadline is None:
        return None
    return {'date': d.design_deadline, 'deliverable_name': d.name}

def _urgency_for(next_deadline, today):
    """
    Computed Urgency - a RAG bucket from how many days away the same next_deadline value actually is.
    Not stored anywhere, it's a pure presentation-layer computation on data we already have.

    Same-day and overdue both bucket into urgent. Overdue pulses, while same day is static.
    """
    if next_deadline is None:
        return None
    days_away = (next_deadline['date'] - today).days
    if days_away < 0:
        return 'overdue'
    if days_away <= 0:
        return 'urgent'
    if days_away <= 2:
        return 'prioritize'
    return 'normal'

# The three possible design disciplines a deliverable can call for — same
# canonical strings used everywhere else in the app (User.team,
# DeliverableAssignment.team, Deliverable.teams). Confirmed against
# projects_detail.py's own team lookups before relying on them here, rather
# than guessing at casing.
TEAM_KEYS = ['2D', '3D', 'Technical']

def _team_columns_for(deliverable):
    """
    Per-deliverable, per-team breakdown for the sublevel table's three team
    columns. For each of 2D/3D/Technical, tells the template one of three
    states:
      - required=False               -> never requested for this deliverable
                                         (template shows "Not Required")
      - required=True, designer=None  -> requested, nobody assigned yet
                                         (template shows "Not Assigned")
      - required=True, designer={...} -> requested and assigned; the chip
                                         itself renders via person_chip()

    Deliverable.teams is just a comma-separated string of what was asked
    for ("3D,Technical") — DeliverableAssignment is the separate record of
    who's actually doing it, so a deliverable can be "requested" for a
    team long before anyone's assigned to it.
    """
    requested = {t.strip() for t in (deliverable.teams or '').split(',') if t.strip()}
    assigned_by_team = {da.team: da.designer for da in deliverable.disciplines}

    columns = {}
    for team in TEAM_KEYS:
        if team not in requested:
            columns[team] = {'required': False, 'designer': None}
        else:
            columns[team] = {'required': True, 'designer': _serialize_person(assigned_by_team.get(team))}
    return columns

def _serialize_deliverable_row(d):
    """
    One row of the fixed-shape deliverable sub-table. Shared by Standard's
    direct project-level expansion and C&CM's per-customer expansion — a
    deliverable looks the same either way once you're this deep, so this
    is the one function both paths call.
    """
    status_label, status_class = derive_deliverable_status(d)
    return {
        'id': d.id,
        'name': d.name,
        'deadline': d.design_deadline,
        'deadline_time': d.design_deadline_time,
        'blanket_status': status_label,
        'status_pill_class': status_class,
        'teams': _team_columns_for(d),
    }

def _parse_ids(param_name):
    """
    Reads a comma-seperated query param of integer IDs (e.g. ?cs_lead=3,7)
    and then returns a list of ints, or an empty list if the param isn't set.
    """

    raw = request.args.get(param_name, '')
    if not raw:
        return []
    return [int(v) for v in raw.split(',') if v.strip().isdigit()]

def _parse_values(param_name):
    """
    Same idea, but for comma-separated string values rather than IDs
    (e.g ?urgency=overdue, urgent or ?status=Active,On Hold).
    """
    raw = request.args.get(param_name, '')
    if not raw:
        return []
    return [v for v in raw.split(',') if v]

def _apply_sql_filters(query, exclude=None):
    """
    Filters that map onto the real Project columns. Cheap to push into SQL,
    rather than fetching every row.

    `exclude` optionally names one filter to skip applying — used when
    computing that filter's own option counts, so a dimension's current
    selection doesn't shrink its own option counts to just itself.
    """
    if exclude != 'cs_lead':
        cs_lead_ids = _parse_ids('cs_lead')
        if cs_lead_ids:
            query = query.filter(Project.cs_lead_id.in_(cs_lead_ids))

    if exclude != 'client':
        client_ids = _parse_ids('client')
        want_client_undefined = _has_undefined('client')
        if client_ids or want_client_undefined:
            conditions = []
            if client_ids:
                conditions.append(Project.client_id.in_(client_ids))
            if want_client_undefined:
                conditions.append(Project.client_id.is_(None))
            query = query.filter(db.or_(*conditions))

    if exclude != 'brief_type':
        brief_types = _parse_values('brief_type')
        if brief_types:
            query = query.filter(Project.brief_type.in_(brief_types))

    if exclude != 'initial_deadline':
        initial_from = _parse_date('initial_deadline_from')
        if initial_from:
            query = query.filter(Project.first_output_deadline >= initial_from)

        initial_to = _parse_date('initial_deadline_to')
        if initial_to:
            query = query.filter(Project.first_output_deadline <= initial_to)

    if exclude != 'search':
        search = request.args.get('search', '').strip()
        if search:
            like = f'%{search}%'
            query = query.filter(db.or_(
                Project.name.ilike(like),
                Project.job_number.ilike(like)
            ))

    return query

def _parse_date(param_name):
    """
    Reads a query param expected to be an ISO date string
    (e.g. ?initial_deadline_from=2026-07-01) and returns a date object,
    or None if the param isn't set or isn't a valid date.
    """
    raw = request.args.get(param_name, '')
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None

def _apply_row_filters(rows, exclude=None):
    """
    Filters that depend on computed values rather than a single column...
    Same `exclude` idea as _apply_sql_filters.
    """
    if exclude != 'designers':
        designer_ids = _parse_ids('designers')
        want_undefined = _has_undefined('designers')
        if designer_ids or want_undefined:
            rows = [r for r in rows if
                    (designer_ids and any(d and d['id'] in designer_ids for d in r['designers']))
                    or (want_undefined and not r['designers'])]

    if exclude != 'status':
        statuses = _parse_values('status')
        if statuses:
            rows = [r for r in rows if r['blanket_status'] in statuses]

    if exclude != 'urgency':
        urgencies = _parse_values('urgency')
        if urgencies:
            rows = [r for r in rows if r['urgency'] in urgencies]

    if exclude != 'team':
        teams = _parse_values('team')
        want_undefined = _has_undefined('team')
        if teams or want_undefined:
            rows = [r for r in rows if
                    any(t in teams for t in r['design_teams'])
                    or (want_undefined and not r['design_teams'])]

    if exclude != 'design_type':
        design_types = _parse_values('design_type')
        want_undefined = _has_undefined('design_type')
        if design_types or want_undefined:
            rows = [r for r in rows if
                    r['design_type'] in design_types
                    or (want_undefined and r['design_type'] is None)]

    if exclude != 'next_deadline':
        next_from = _parse_date('next_deadline_from')
        if next_from:
            rows = [r for r in rows if r['next_deadline'] and r['next_deadline']['date'] >= next_from]

        next_to = _parse_date('next_deadline_to')
        if next_to:
            rows = [r for r in rows if r['next_deadline'] and r['next_deadline']['date'] <= next_to]

    return rows

def _base_query_for_view(view, user):
    """
    Returns (query, order_by) for whichever of the three fixed views is
    active, before any of the combinable filters are applied. Pulled out
    of index() so the same view-scoping logic can be reused when computing
    each filter option's count — those counts need to be scoped to "this
    view" too, not the whole projects table.
    """
    order_by = Project.first_output_deadline.asc()

    # A saved custom view ("view-<id>") isn't itself a base query — it's a
    # name + a remembered filter selection layered on top of one of the
    # three fixed presets. Resolve it down to that preset here so every
    # other branch below only ever has to know about 'my'/'all'/'design_complete'.
    if view.startswith('view-'):
        try:
            view_id = int(view.split('-', 1)[1])
        except ValueError:
            view_id = None
        saved_view = ProjectTableView.query.filter_by(id=view_id, user_id=user.id).first() if view_id else None
        view = saved_view.base_view if saved_view else 'my'

    # 'approved' (the raw status value) is a transient in-flight status now
    # (M8 added Pre-Production/Handed to Production after it), not a finish
    # line — so as of 18 Aug 2026 it's no longer excluded from My/All. Only
    # 'handed_to_production' (the real terminal state) is excluded, matching
    # dashboard.py's _scoped_projects(). A user who wants a "Client Approved
    # only" list can now build it themselves: My or All + Status filter =
    # "Client Approved", saved as a custom view — see the 'design_complete'
    # branch below for the one fixed tab that still hardcodes a status. That
    # VIEW KEY was renamed from 'approved' to 'design_complete' on 18 Aug
    # 2026 too (was confusing next to the now-unrelated 'approved' status
    # value) — see migrations/_backfill_project_table_view_base_view.py for
    # the one-time rename of any already-saved views built on top of it.
    if view == 'all':
        if user.role in ('cs', 'admin', 'management', 'project_owner'):
            query = Project.query.filter(
                Project.project_status != 'draft',
                Project.project_status != 'handed_to_production'
            )
        elif user.team:
            query = Project.query.filter(
                Project.design_teams_requested.contains(user.team),
                Project.project_status != 'draft',
                Project.project_status != 'handed_to_production'
            )
        else:
            query = None

    elif view == 'design_complete':
        # Fixed tab relabeled "Design Complete" in the UI, and its view key
        # renamed from 'approved' to 'design_complete' to match (18 Aug 2026,
        # per Ezekiel — "approved" the raw status is temporary/in-flight now,
        # "handed to production" is the real finish line, and keeping the
        # view key as 'approved' next to that was confusing). Ordered by
        # when each project most recently logged 'handed_to_production'
        # (Project has no dedicated timestamp column for this stage, unlike
        # approved_at) — most recently completed first, same intent as the
        # old approved_at.desc().
        handed_at = (
            db.session.query(db.func.max(ProjectStatusLog.started_at))
            .filter(
                ProjectStatusLog.project_id == Project.id,
                ProjectStatusLog.status == 'handed_to_production'
            )
            .correlate(Project)
            .scalar_subquery()
        )
        query = Project.query.filter_by(project_status='handed_to_production')
        order_by = handed_at.desc()

    else:  # 'my' - default
        if user.role in ('cs', 'admin', 'management', 'project_owner'):
            if user.role == 'admin':
                query = Project.query.filter(
                    Project.project_status != 'draft',
                    Project.project_status != 'handed_to_production'
                )
            else:
                secondary_project_ids = db.session.query(ProjectSecondaryCS.project_id).filter_by(
                    user_id=user.id
                ).subquery()
                query = Project.query.filter(
                    db.or_(
                        Project.cs_lead_id == user.id,
                        Project.id.in_(secondary_project_ids),
                        Project.project_owner_id == user.id
                    ),
                    Project.project_status != 'draft',
                    Project.project_status != 'handed_to_production'
                )
        else:
            assigned_project_ids = db.session.query(ProjectDesigner.project_id).filter_by(
                user_id=user.id
            ).subquery()
            query = Project.query.filter(
                Project.id.in_(assigned_project_ids),
                Project.project_status != 'draft',
                Project.project_status != 'handed_to_production'
            )

    # Cancelled projects are hidden from every view by default (they still
    # exist, still show up on refresh, just not by default) — the toolbar
    # toggle or the Cancelled status chip (_show_cancelled()) opts back in.
    # Applied once here rather than per-branch so all three presets, the
    # filter-count recompute, and the view-total count can never disagree
    # on whether cancelled projects are in scope.
    if query is not None and not _show_cancelled():
        query = query.filter(Project.cancelled_at.is_(None))

    return query, order_by

def _rows_excluding(view, user, exclude):
    """
    Rebuilds the row list for the current view, with every active filter
    applied EXCEPT `exclude`. Used to compute one filter's own option
    counts — a project should still count toward "Client: Acme" even
    while Client is the very filter being counted, as long as it matches
    every OTHER active filter.
    """
    sql_dims = ('cs_lead', 'client', 'brief_type', 'initial_deadline', 'search')
    row_dims = ('designers', 'status', 'urgency', 'next_deadline', 'team', 'design_type')

    query, order_by = _base_query_for_view(view, user)
    if query is None:
        return []

    query = _apply_sql_filters(query, exclude=exclude if exclude in sql_dims else None)
    projects = query.order_by(order_by).all()

    rows = [_serialize_row(p) for p in projects]
    rows = _apply_row_filters(rows, exclude=exclude if exclude in row_dims else None)
    return rows

def _count_by_id(rows, key):
    """Counts rows by a single-person field (e.g. row['cs_lead']). Rows
    with no one set for this field just don't contribute to any count."""
    counts = {}
    for r in rows:
        person = r[key]
        if person:
            counts[person['id']] = counts.get(person['id'], 0) + 1
    return counts

def _count_by_id_list(rows, key):
    """Same idea, but for a field that's a list of people (Designers) —
    a project with 2 designers counts toward both of them."""
    counts = {}
    for r in rows:
        for person in r[key]:
            if person:
                counts[person['id']] = counts.get(person['id'], 0) + 1
    return counts

def _count_by_value(rows, key):
    """Counts rows by a plain scalar already on the row (client_id,
    brief_type, blanket_status, urgency)."""
    counts = {}
    for r in rows:
        value = r[key]
        if value is not None:
            counts[value] = counts.get(value, 0) + 1
    return counts

def _show_cancelled():
    """True if the Cancelled status filter is active. Cancelled projects
    are excluded from every view by default (see the exclusion in
    _base_query_for_view) — this is the only way back in. There's no
    separate "show cancelled" query param: the Show Cancelled toolbar
    button is just a shortcut that sets ?status=Cancelled (same as picking
    the Cancelled chip in the filter panel by hand), so it composes with
    every other filter dimension for free, and doubles as "cancelled
    projects ONLY" rather than "cancelled mixed in with everything else" —
    the row-level status filter (_apply_row_filters) already narrows to
    exactly the selected status value(s)."""
    return 'Cancelled' in _parse_values('status')

def _has_undefined(param_name):
    """
    True if the admin-only 'undefined' sentinel is among a filter param's
    comma-separated values (e.g. ?client=3,undefined). Checked separately
    from _parse_ids/_parse_values, which only ever pull out real ids/values
    - a non-digit, non-matching string like "undefined" just gets silently
    dropped by those. This reads the same raw param a second time, looking
    only for that one sentinel.
    """
    raw = request.args.get(param_name, '')
    return 'undefined' in [v.strip() for v in raw.split(',') if v.strip()]

def _count_undefined(rows, key):
    """
    Counts rows where this field is missing entirely - None for a
    single-value field (Client, Type of Design), or an empty list for a
    multi-value one (Designers, Team). Powers the Undefined chip's live
    count - callers merge this into a normal counts dict under a None key,
    so the template reads it with the exact same .get(None, 0) every
    other option already uses.
    """
    return sum(1 for r in rows if not r[key])

def _count_by_list_membership(rows, key):
    """Counts rows by membership in a list-of-strings field (e.g. row['design_teams']
    contains '2D') - same idea as _count_by_id_list, but for plain string
    values rather than person dicts."""
    counts = {}
    for r in rows:
        for value in r[key]:
            counts[value] = counts.get(value, 0) + 1
    return counts


def _build_filter_counts(view, user):
    """
    Computes every filter option's live count, each scoped to "this view
    plus every other currently active filter."
    """
    client_rows = _rows_excluding(view, user, 'client')
    designer_rows = _rows_excluding(view, user, 'designers')
    design_type_rows = _rows_excluding(view, user, 'design_type')

    client_counts = _count_by_value(client_rows, 'client_id')
    client_counts[None] = _count_undefined(client_rows, 'client_id')

    designer_counts = _count_by_id_list(designer_rows, 'designers')
    designer_counts[None] = _count_undefined(designer_rows, 'designers')

    design_type_counts = _count_by_value(design_type_rows, 'design_type')
    design_type_counts[None] = _count_undefined(design_type_rows, 'design_type')

    team_rows = _rows_excluding(view, user, 'team')
    team_counts = _count_by_list_membership(team_rows, 'design_teams')
    team_counts[None] = _count_undefined(team_rows, 'design_teams')
    

    return {
        'cs_lead': _count_by_id(_rows_excluding(view, user, 'cs_lead'), 'cs_lead'),
        'designers': designer_counts,
        'client': client_counts,
        'brief_type': _count_by_value(_rows_excluding(view, user, 'brief_type'), 'brief_type'),
        'status': _count_by_value(_rows_excluding(view, user, 'status'), 'blanket_status'),
        'urgency': _count_by_value(_rows_excluding(view, user, 'urgency'), 'urgency'),
        'team': _count_by_list_membership(_rows_excluding(view, user, 'team'), 'design_teams'),
        'design_type': design_type_counts,
    }

def _serialize_row(p):
    """Turns one Project into the flat dict the template needs. Pulled out of index(), now that there are three different queries feeding
    in the same row shape.""" 
    next_deadline = _next_deadline_for(Deliverable.query.filter_by(project_id=p.id))
    status_label, status_class = derive_project_status(p)
    return {
        'id': p.id,
        'name': p.name,
        'client': p.client_brand.name if p.client_brand else None,
        'client_id': p.client_id,
        'job_number': p.job_number,
        'cs_lead': _serialize_person(p.cs_lead),
        'designers': [_serialize_person(pd.designer) for pd in p.assigned_designers],
        'design_teams': [t.strip() for t in (p.design_teams_requested or '').split(',') if t.strip()],
        'design_type': 'ccm' if p.brief_type == 'ccm' else (str(p.design_type_id) if p.design_type_id else None),
        'initial_deadline': p.first_output_deadline,
        'status': p.project_status,
        'blanket_status': status_label,
        'status_pill_class': status_class,
        'brief_type': p.brief_type,
        'rollup': _rollup_for(Deliverable.query.filter_by(project_id=p.id)),
        'customer_count': sum(1 for pc in p.project_customers if not pc.cancelled) if p.brief_type == 'ccm' else None,
        'next_deadline': next_deadline,
        'urgency': _urgency_for(next_deadline, date.today()),
    }

def _compute_rows_and_groups(view, user):
    """
    The rows -> filter -> sort -> group pipeline, shared by index() and
    table_rows() (added for task #55's SSE-triggered live table refresh —
    see project_list.js's refreshProjectTable() and polling.js's
    .project-list-page branch). Pulled out so the live-refresh endpoint can
    never quietly drift out of sync with what a real page load computes —
    same principle as _base_query_for_view/_rows_excluding already being
    shared rather than re-derived per caller.
    """
    query, order_by = _base_query_for_view(view, user)

    if query is None:
        rows = []
    else:
        query = _apply_sql_filters(query)
        projects = query.order_by(order_by).all()
        rows = [_serialize_row(p) for p in projects]
        rows = _apply_row_filters(rows)

    # Sort is applied last, after every filter — it re-orders whatever
    # subset of rows is already showing, it never changes which rows show.
    sort_field = request.args.get('sort', '')
    sort_dir = request.args.get('dir', 'asc') if sort_field else ''
    if sort_field in SORT_FIELDS:
        rows = _sort_rows(rows, sort_field, sort_dir)
    else:
        # Unknown/garbage ?sort= value — fall back to the view's default
        # order rather than silently sorting by a field that doesn't exist.
        sort_field = ''
        sort_dir = ''

    # Group by is independent of Sort - a separate `group` query param, and
    # the two can both be active at once. Grouping buckets the already-
    # sorted rows into named boxes; a row's position relative to its own
    # group's other rows is untouched, since Python's sort (above) is
    # stable and grouping never re-sorts within a group.
    group_field = request.args.get('group', '')
    if group_field in dict(GROUP_FIELDS):
        groups = _group_rows(rows, group_field)
    else:
        group_field = ''
        groups = None

    return rows, groups, sort_field, sort_dir, group_field


@project_list_bp.route('/table-rows')
@login_required
def table_rows():
    """
    Stage 3 of task #55 (SSE live updates) — the Projects table's own
    refresh endpoint. sse.py's /sse/dashboard is a generic "some project
    changed somewhere" doorbell (same one the old and new dashboards
    already listen to); on a ping, the client re-fetches this with its
    current view/filter/sort/group query params still attached and swaps
    the result straight into #project-table, leaving the rest of the page
    (toolbar, filter panel, any open overlay) completely untouched. See
    project_list.js's refreshProjectTable() and project_list_layout.js's
    bindColumnControls() (re-run after the swap, since resize/reorder
    listeners are bound directly to header cells, not delegated) for the
    two pieces that make that swap safe without a full page reload.

    Deliberately does NOT touch session['last_project_view'] the way
    index() does — a background live-update ping should never change what
    the user would land on next time they click the sidebar's Projects
    link, only index() (a real navigation) should do that.
    """
    user = _effective_user()
    view = request.args.get('view') or session.get('last_project_view', 'my')
    rows, groups, sort_field, sort_dir, group_field = _compute_rows_and_groups(view, user)
    return render_template('project_list/_table_rows.html', rows=rows, groups=groups, today=date.today())


@project_list_bp.route('/')
@login_required
def index():
    """ Three fixes presets. Set now as we build it out"""
    user = _effective_user()
    # Remember which tab the user was last on (per Ezekiel, 19 Aug 2026) —
    # the sidebar's "Projects" link is a static href with no query string,
    # so a plain visit here would otherwise always default to 'my' instead
    # of wherever they left off. Session-scoped, not a DB column: meant to
    # survive across navigations in one browsing session, not follow the
    # user to a different device or across a logout.
    view = request.args.get('view')
    if view:
        session['last_project_view'] = view
    else:
        view = session.get('last_project_view', 'my')

    # Fresh landing on a saved view (just clicked its tab, no filter params
    # yet) - replay its saved filters as real query params via a redirect,
    # so every existing filter/sort/group code path (all of which read from
    # request.args) picks them up for free instead of needing its own
    # separate "saved filter" code path. `len(request.args) <= 1` is the
    # "fresh landing" check - only `view` itself is present so far.
    if view.startswith('view-') and len(request.args) <= 1:
        try:
            view_id = int(view.split('-', 1)[1])
        except ValueError:
            view_id = None
        saved_view = ProjectTableView.query.filter_by(id=view_id, user_id=user.id).first() if view_id else None
        if saved_view is not None and saved_view.filters:
            params = dict(saved_view.filters)
            params['view'] = view
            return redirect(url_for('project_list.index', **params))

    table_key = f'project_list:{view}'

    layout_row = UserTableLayout.query.filter_by(user_id=user.id, table_key=table_key).first()
    saved_layout = layout_row.layout if layout_row else None

    deliverable_layout_row = UserTableLayout.query.filter_by(user_id=user.id, table_key='project_list:deliverable_table').first()
    saved_deliverable_layout = deliverable_layout_row.layout if deliverable_layout_row else None
    customer_layout_row = UserTableLayout.query.filter_by(user_id=user.id, table_key='project_list:customer_table').first()
    saved_customer_layout = customer_layout_row.layout if customer_layout_row else None
    
    rows, groups, sort_field, sort_dir, group_field = _compute_rows_and_groups(view, user)

    filter_counts = _build_filter_counts(view, user)

    view_total_query, _ = _base_query_for_view(view, user)
    view_total = view_total_query.count() if view_total_query is not None else 0

    filter_options = {
        'cs_leads': UserModel.query.filter(UserModel.role.in_(['cs', 'admin'])).order_by(UserModel.name).all(),
        'designers': UserModel.query.filter(UserModel.role.in_(['designer', 'team_lead'])).order_by(UserModel.name).all(),
        'clients': Client.query.order_by(Client.name).all(),
        'brief_types': [('standard', 'Standard'), ('ccm', 'C&CM')],
        # 'In Progress' removed (13 Aug 2026) — the C&CM aggregate's "In
        # Progress" stage was renamed to "In Design" to match Standard's
        # wording (status_vocabulary.py), so it's no longer a distinct
        # blanket_status value to filter on.
        'statuses': [
            'Briefed', 'In Design', 'Client Approved', 'Pre-Production', 'Handed to Production',
            'Design Completed', 'On Hold', 'Cancelled',
        ],
        'urgencies': [('overdue', 'Overdue'), ('urgent', 'Urgent'), ('prioritize', 'Prioritize'), ('normal', 'Normal')],
        'teams': TEAM_KEYS,
        'design_types': [('ccm', 'C&CM')] + [(str(dt.id), dt.name) for dt in DesignType.query.order_by(DesignType.name).all()],
    }

    active_filters = {
        'cs_lead': _parse_ids('cs_lead'),
        'client': _parse_ids('client'),
        'designers': _parse_ids('designers'),
        'brief_type': _parse_values('brief_type'),
        'status': _parse_values('status'),
        'urgency': _parse_values('urgency'),
        'team': _parse_values('team'),
        'design_type': _parse_values('design_type'),
        'client_undefined': _has_undefined('client'),
        'designers_undefined': _has_undefined('designers'),
        'team_undefined': _has_undefined('team'),
        'design_type_undefined': _has_undefined('design_type'),
        'search': request.args.get('search', '').strip(),
        'initial_deadline_from': request.args.get('initial_deadline_from', ''),
        'initial_deadline_to': request.args.get('initial_deadline_to', ''),
        'next_deadline_from': request.args.get('next_deadline_from', ''),
        'next_deadline_to': request.args.get('next_deadline_to', ''),
    }

    active_filter_count = sum([
        bool(active_filters['cs_lead']),
        bool(active_filters['client']),
        bool(active_filters['designers']),
        bool(active_filters['brief_type']),
        bool(active_filters['status']),
        bool(active_filters['urgency']),
        bool(active_filters['team']),
        bool(active_filters['design_type']),
        bool(active_filters['initial_deadline_from'] or active_filters['initial_deadline_to']),
        bool(active_filters['next_deadline_from'] or active_filters['next_deadline_to']),
    ])

    # Saved-view tabs (rendered after the 3 fixed presets) and which fixed
    # preset the CURRENTLY active view is built on - the latter is what the
    # "Save as new view" popover submits as `base_view` when the user isn't
    # already sitting on a saved view of their own.
    saved_views = ProjectTableView.query.filter_by(user_id=user.id).order_by(ProjectTableView.created_at.asc()).all()
    if view.startswith('view-'):
        try:
            active_view_id = int(view.split('-', 1)[1])
        except ValueError:
            active_view_id = None
        active_saved_view = ProjectTableView.query.filter_by(id=active_view_id, user_id=user.id).first() if active_view_id else None
        current_base_view = active_saved_view.base_view if active_saved_view else 'my'
    else:
        active_saved_view = None
        current_base_view = view

    # Dirty = the current filters/sort/group no longer what is active in the tab. 
    # Column layout is not included, that preference is saved seperately and persistent across all tabs.
    current_params = {k: v for k, v in request.args.items() if k!= 'view' and v}
    baseline_params = dict(active_saved_view.filters) if active_saved_view and active_saved_view.filters else {}
    is_dirty = current_params != baseline_params

    return render_template('project_list/index.html', rows=rows, view=view, effective_role=user.role, today=date.today(), filter_options=filter_options,
                       active_filters=active_filters, filter_counts=filter_counts, view_total=view_total, table_key=table_key, saved_layout=saved_layout, active_filter_count=active_filter_count,
                       saved_deliverable_layout=saved_deliverable_layout, saved_customer_layout=saved_customer_layout, is_admin=(user.role == 'admin'),
                       sort_options=SORT_OPTIONS, sort_field=sort_field, sort_dir=sort_dir,
                       saved_views=saved_views, current_base_view=current_base_view, is_dirty=is_dirty,
                       group_options=GROUP_FIELDS, group_field=group_field, groups=groups, show_cancelled=_show_cancelled(), )

@project_list_bp.route('/layout', methods=['POST'])
@login_required
def save_layout():
    """
    Silently persists one user's column widths/order for one table+view.
    Called after every resize/reorder, debounced client-side so this fires
    once things settle rather than on every pixel of a drag.
    """
    user = _effective_user()
    data = request.get_json(silent=True) or {}
    table_key = data.get('table_key')
    layout = data.get('layout')

    if not table_key or not isinstance(layout, list) or not layout:
        return jsonify({'error': 'invalid payload'}), 400

    row = UserTableLayout.query.filter_by(user_id=user.id, table_key=table_key).first()
    if row:
        row.layout = layout
    else:
        row = UserTableLayout(user_id=user.id, table_key=table_key, layout=layout)
        db.session.add(row)
    db.session.commit()

    return jsonify({'status': 'ok'})


@project_list_bp.route('/<int:project_id>/expand')
@login_required
def expand(project_id):
    project = Project.query.get_or_404(project_id)

    if project.brief_type == 'ccm':
        rows = []
        for pc in project.project_customers:
            if pc.cancelled:
                continue
            status_label, status_class = derive_customer_pipeline_status(pc)
            rows.append({
                'label': pc.customer.name,
                'design_deadline': pc.design_deadline,
                'installation_date': pc.installation_date,
                'deliverable_count': len(pc.deliverables),
                'revision_count': pc.posm_revision_count,
                'blanket_status': status_label,
                'status_pill_class': status_class,
                'expand_url': url_for('project_list.expand_customer', project_customer_id=pc.id),
            })
        return render_template('project_list/_expand_rows.html', rows=rows, today=date.today())

    rows = [_serialize_deliverable_row(d) for d in project.project_deliverables]
    return render_template('project_list/_deliverable_table.html', rows=rows, today=date.today(), brief_type='standard')

@project_list_bp.route('/customer/<int:project_customer_id>/expand')
@login_required
def expand_customer(project_customer_id):
    """
    Sublevel 2, C&CM only: one customer's own deliverables. Same on-
    demand/fetch-once principle as expand() above — built and sent down
    the wire only once someone actually clicks that customer's toggle.
    """
    pc = ProjectCustomer.query.get_or_404(project_customer_id)
    rows = [_serialize_deliverable_row(d) for d in pc.deliverables]
    return render_template('project_list/_deliverable_table.html', rows=rows, today=date.today(), brief_type='ccm')

def _rollup_for(deliverable_query):
    """ The computed rollup: Shows how many of this projects deliverables are Approved out of the total."""

    deliverables = deliverable_query.all()
    total = len(deliverables)
    if total == 0:
        return None
    approved = sum(1 for d in deliverables if d.status == 'approved')
    return f'{approved} of {total} Approved'


# ---- Sorting ----
# Every sort dimension a user can pick from the Sort popout, in display
# order. Kept as a plain (value, label) list (not a dict) so the template
# can render them in a fixed, deliberate order rather than whatever order
# a dict happens to iterate in.
SORT_OPTIONS = [
    ('name', 'Project Name'),
    ('client', 'Client'),
    ('cs_lead', 'CS Lead'),
    ('initial_deadline', 'Initial Deadline'),
    ('next_deadline', 'Next Deadline'),
    ('urgency', 'Urgency'),
    ('status', 'Status'),
    ('job', 'Job Number'),
]

# "Most urgent first" order for the Urgency sort option — lower sorts first.
# A project with no urgency (no next deadline at all) is deliberately last,
# in the same spot an undated deadline would land.
_URGENCY_SORT_ORDER = {'overdue': 0, 'urgent': 1, 'prioritize': 2, 'normal': 3}

# One key-function per sortable field, each taking (row, reverse) -> a
# sortable value. `reverse` is only actually used by the two date fields:
# a project with no deadline set should always sort to the END of the
# list, in EITHER direction — without this, sorted(..., reverse=True)
# would take a "no deadline = date.max" sentinel and flip it to the very
# front once you switch to descending, which reads as a bug, not a
# feature. Using date.min as the sentinel specifically when reverse=True
# keeps undated rows pinned last regardless of which arrow was clicked.
SORT_FIELDS = {
    'name': lambda r, reverse: (r['name'] or '').lower(),
    'client': lambda r, reverse: (r['client'] or '').lower(),
    'cs_lead': lambda r, reverse: (r['cs_lead']['name'].lower() if r['cs_lead'] else ''),
    'initial_deadline': lambda r, reverse: r['initial_deadline'] or (date.min if reverse else date.max),
    'next_deadline': lambda r, reverse: (r['next_deadline']['date'] if r['next_deadline'] else (date.min if reverse else date.max)),
    'urgency': lambda r, reverse: _URGENCY_SORT_ORDER.get(r['urgency'], 4),
    'status': lambda r, reverse: (r['blanket_status'] or '').lower(),
    'job': lambda r, reverse: (r['job_number'] or '').lower(),
}

def _sort_rows(rows, field, direction):
    """
    Sorts the already-filtered row list in Python, not SQL. Several
    sortable fields (urgency, next_deadline, the cs_lead person dict) are
    computed in _serialize_row()/_urgency_for(), not real Project columns
    — there's no SQL expression to ORDER BY for them. Sorting the final
    row list once, here, keeps every sortable field (real column or
    computed) going through the exact same code path instead of splitting
    sorting between a SQL branch and a Python branch depending on the field.
    """
    key_fn = SORT_FIELDS.get(field)
    if key_fn is None:
        return rows
    reverse = direction == 'desc'
    return sorted(rows, key=lambda r: key_fn(r, reverse), reverse=reverse)


# ---- Grouping ----
# Every dimension a user can group rows by, in display order. Independent
# of Sort (`group` and `sort` are separate query params, and both can be
# active at once) - Group by buckets rows into named boxes; whichever sort
# is active still runs first, so a group's own rows stay in that order.
GROUP_FIELDS = [
    ('cs_lead', 'CS Lead'),
    ('client', 'Client'),
    ('team', 'Team'),
    ('urgency', 'Urgency'),
    ('status', 'Status'),
]

def _group_key_and_label(row, field):
    """
    Returns (sort_key, label) for the single-value group fields. `team` is
    handled separately in _group_rows, since it's the one multi-value field
    here - a row can legitimately belong to more than one team's group at
    once (a project requesting both 2D and 3D design).
    """
    if field == 'cs_lead':
        person = row['cs_lead']
        return ((0, person['name'].lower()), person['name']) if person else ((1, ''), 'No CS Lead')
    if field == 'client':
        return ((0, row['client'].lower()), row['client']) if row['client'] else ((1, ''), 'No Client')
    if field == 'urgency':
        order = _URGENCY_SORT_ORDER.get(row['urgency'], 4)
        label = (row['urgency'] or 'normal').capitalize()
        return ((order,), label)
    if field == 'status':
        return ((row['blanket_status'].lower(),), row['blanket_status'])
    return None

def _group_rows(rows, field):
    """
    Buckets an already-filtered (and already-sorted) row list into named
    groups for whichever field the user picked in the Group by panel. Each
    row keeps its position relative to its own group's other rows - Group
    by changes how rows are BOXED, not the order they're compared in.

    Returns a list of {'key', 'label', 'rows'} dicts, one per group, in
    display order (alphabetical/urgency-order by label, except `team`
    which follows the fixed TEAM_KEYS order plus a trailing Undefined box).

    `team` fans a row out into every team-group it belongs to, since
    design_teams is a list, not a single value - a project requesting both
    2D and 3D legitimately shows up in both boxes.
    """
    if field == 'team':
        buckets = {team: [] for team in TEAM_KEYS}
        undefined_bucket = []
        for row in rows:
            teams = row['design_teams']
            if not teams:
                undefined_bucket.append(row)
                continue
            for team in teams:
                buckets.setdefault(team, [])
                buckets[team].append(row)
        groups = [{'key': t, 'label': t, 'rows': buckets[t]} for t in TEAM_KEYS if buckets[t]]
        if undefined_bucket:
            groups.append({'key': None, 'label': 'Undefined', 'rows': undefined_bucket})
        return groups

    groups = {}
    order = []
    for row in rows:
        result = _group_key_and_label(row, field)
        if result is None:
            return [{'key': None, 'label': None, 'rows': rows}]
        sort_key, label = result
        if label not in groups:
            groups[label] = {'sort_key': sort_key, 'rows': []}
            order.append(label)
        groups[label]['rows'].append(row)

    order.sort(key=lambda label: groups[label]['sort_key'])
    return [{'key': label, 'label': label, 'rows': groups[label]['rows']} for label in order]


@project_list_bp.route('/views', methods=['POST'])
@login_required
def create_view():
    """
    Saves the current filter selection (whatever's active right now) as a
    new named tab, layered on top of one of the three fixed presets. The
    frontend submits `base_view` (the preset the user is currently sitting
    on, or already sitting on top of if they're on another saved view) and
    `filters` (the current page's own query params, minus `view` itself).
    """
    user = _effective_user()
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    base_view = data.get('base_view') or 'my'
    filters = data.get('filters') or {}

    if not name:
        return jsonify({'error': 'name is required'}), 400
    if base_view not in ('my', 'all', 'design_complete'):
        base_view = 'my'

    view = ProjectTableView(user_id=user.id, name=name, base_view=base_view, filters=filters)
    db.session.add(view)
    db.session.commit()

    return jsonify({'status': 'ok', 'id': view.id, 'name': view.name})


@project_list_bp.route('/views/<int:view_id>/rename', methods=['POST'])
@login_required
def rename_view(view_id):
    user = _effective_user()
    view = ProjectTableView.query.filter_by(id=view_id, user_id=user.id).first_or_404()
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400

    view.name = name
    db.session.commit()
    return jsonify({'status': 'ok'})


@project_list_bp.route('/views/<int:view_id>/delete', methods=['POST'])
@login_required
def delete_view(view_id):
    user = _effective_user()
    view = ProjectTableView.query.filter_by(id=view_id, user_id=user.id).first_or_404()
    db.session.delete(view)
    db.session.commit()
    return jsonify({'status': 'ok'})

