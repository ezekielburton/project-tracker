#   app/routes/project_list.py
#   
#   Rewrite of the projects page. Replaces main.projects() and its three role branched render targets
#   All now within one template that adapts to the viewing user's role, per app architecture

from datetime import date
from flask import Blueprint, render_template, session, request, jsonify, url_for, redirect
from flask_login import login_required, current_user
from sqlalchemy import nullslast
from app import db
from app.models import Project, ProjectSecondaryCS, ProjectDesigner, Deliverable, User as UserModel, Client, UserTableLayout, ProjectCustomer, DesignType, ProjectTableView

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

SORT_FIELDS = [
    ('initial_deadline', 'Initial Deadline'),
    ('next_deadline', 'Next Deadline'),
    ('name', 'Name'),
]

GROUP_FIELDS = [
    ('cs_lead', 'CS Lead'),
    ('client', 'Client'),
    ('team', 'Design Team'),
    ('urgency', 'Urgency'),
    ('status', 'Status'),
]

URGENCY_ORDER = ['overdue', 'urgent', 'prioritize', 'normal']
URGENCY_LABELS = {'overdue': 'Overdue', 'urgent': 'Urgent', 'prioritize': 'Prioritize', 'normal': 'Normal'}
STATUS_ORDER = ['Not Started', 'Active', 'On Hold', 'Completed']

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
    return {
        'id': d.id,
        'name': d.name,
        'deadline': d.design_deadline,
        'deadline_time': d.design_deadline_time,
        'blanket_status': _blanket_status(d.status),
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

def _sort_rows(rows, sort_field, direction):
    """
    Sorts the already-filtered rows for either the flat table or (when a
    group is also active) for the position inside each group — same
    function either way, since grouping happens after this and Python's
    sort is stable, so rows keep this order once they're bucketed.
    """
    reverse = direction == 'desc'

    if sort_field == 'name':
        return sorted(rows, key=lambda r: (r['name'] or '').lower(), reverse=reverse)

    if sort_field in ('initial_deadline', 'next_deadline'):
        def get_date(r):
            if sort_field == 'next_deadline':
                return r['next_deadline']['date'] if r['next_deadline'] else None
            return r['initial_deadline']

        # Rows with no date at all always trail at the bottom, regardless
        # of which direction you picked — "soonest first" and "latest
        # first" both mean undated rows aren't the answer to the question.
        with_date = [r for r in rows if get_date(r) is not None]
        without_date = [r for r in rows if get_date(r) is None]
        with_date.sort(key=get_date, reverse=reverse)
        return with_date + without_date

    return rows


def _group_rows(rows, group_field):
    """
    Buckets already-sorted rows into named groups for the collapsible
    group-table view. Every dimension puts each row in exactly one
    bucket, except Design Team — a project can be both 2D and 3D, so it
    lands in both of those groups.
    """
    buckets = {}

    def add(key, label, row):
        if key not in buckets:
            buckets[key] = {'key': key, 'label': label, 'rows': []}
        buckets[key]['rows'].append(row)

    if group_field == 'cs_lead':
        for r in rows:
            if r['cs_lead']:
                add(r['cs_lead']['id'], r['cs_lead']['name'], r)
            else:
                add('undefined', 'CS Unassigned', r)

    elif group_field == 'client':
        for r in rows:
            if r['client']:
                add(r['client_id'], r['client'], r)
            else:
                add('undefined', 'Client Missing', r)

    elif group_field == 'team':
        for r in rows:
            if r['design_teams']:
                for team in r['design_teams']:
                    add(team, team, r)
            else:
                add('undefined', 'Team Unassigned', r)

    elif group_field == 'urgency':
        for r in rows:
            if r['urgency']:
                add(r['urgency'], URGENCY_LABELS[r['urgency']], r)
            else:
                add('undefined', 'No Deadline', r)

    elif group_field == 'status':
        for r in rows:
            add(r['blanket_status'], r['blanket_status'], r)

    groups = list(buckets.values())

    # The buckets themselves need an order too. Urgency/Status/Team have a
    # real order (severity, workflow stage, canonical team list) that
    # isn't A-Z; CS Lead/Client just go alphabetical, with "undefined"
    # pinned last no matter which dimension it's for.
    fixed_order = {'urgency': URGENCY_ORDER, 'status': STATUS_ORDER, 'team': TEAM_KEYS}
    if group_field in fixed_order:
        order = fixed_order[group_field]
        groups.sort(key=lambda g: order.index(g['key']) if g['key'] in order else len(order))
    else:
        groups.sort(key=lambda g: (g['key'] == 'undefined', g['label'].lower()))

    return groups

def _base_query_for_view(view, user):
    """
    Returns (query, order_by) for whichever of the three fixed views is
    active, before any of the combinable filters are applied. Pulled out
    of index() so the same view-scoping logic can be reused when computing
    each filter option's count — those counts need to be scoped to "this
    view" too, not the whole projects table.
    """
    order_by = Project.first_output_deadline.asc()

    if view.startswith('view-'):
        try:
            saved_view_id = int(view[len('view-'):])
        except ValueError:
            saved_view_id = None
        saved_view = (
            ProjectTableView.query.filter_by(id=saved_view_id, user_id=user.id).first()
            if saved_view_id else None
        )

        return _base_query_for_view(saved_view.base_view if saved_view else 'my', user)
 
    if view == 'all':
        if user.role in ('cs', 'admin', 'management'):
            query = Project.query.filter(
                Project.project_status != 'draft',
                Project.project_status != 'approved'
            )
        elif user.team:
            query = Project.query.filter(
                Project.design_teams_requested.contains(user.team),
                Project.project_status != 'draft',
                Project.project_status != 'approved'
            )
        else:
            query = None

    elif view == 'approved':
        query = Project.query.filter_by(project_status='approved')
        order_by = Project.approved_at.desc()

    else:  # 'my' - default
        if user.role in ('cs', 'admin', 'management'):
            if user.role == 'admin':
                query = Project.query.filter(
                    Project.project_status != 'draft',
                    Project.project_status != 'approved'
                )
            else:
                secondary_project_ids = db.session.query(ProjectSecondaryCS.project_id).filter_by(
                    user_id=user.id
                ).subquery()
                query = Project.query.filter(
                    db.or_(
                        Project.cs_lead_id == user.id,
                        Project.id.in_(secondary_project_ids)
                    ),
                    Project.project_status != 'draft',
                    Project.project_status != 'approved'
                )
        else:
            assigned_project_ids = db.session.query(ProjectDesigner.project_id).filter_by(
                user_id=user.id
            ).subquery()
            query = Project.query.filter(
                Project.id.in_(assigned_project_ids),
                Project.project_status != 'draft',
                Project.project_status != 'approved'
            )

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
        'blanket_status': _blanket_status(p.project_status),
        'brief_type': p.brief_type,
        'rollup': _rollup_for(Deliverable.query.filter_by(project_id=p.id)),
        'customer_count': sum(1 for pc in p.project_customers if not pc.cancelled) if p.brief_type == 'ccm' else None,
        'next_deadline': next_deadline,
        'urgency': _urgency_for(next_deadline, date.today()),
    }

@project_list_bp.route('/')
@login_required
def index():
    """ Three fixes presets. Set now as we build it out"""
    user = _effective_user()
    view = request.args.get('view', 'my')

    # Landing on a custom view fresh - Redirect once. From that point on this is just a normal
    # filtered request; every existing _parse_ids/_parse_values/chip-highlight call works
    # completely unchanged, since the saved filters are the query string

    if view.startswith('view-'):
        has_filter_params = any (
            k in request.args for k in
            ('cs_lead', 'client', 'designers', 'brief_type', 'status', 'urgency', 'team', 'design_type', 'search',
             'initial_deadline_from', 'initial_deadline', 'initial_deadline_to', 'next_deadline_from', 'next_deadline_to')
        )
        if not has_filter_params:
            try:
                saved_view_id = int(view[len('view-'):])
            except ValueError:
                saved_view_id = None
            saved_view = (
                ProjectTableView.query.filter_by(id=saved_view_id, user_id=user.id).first()
                if saved_view_id else None
            )
            if saved_view and saved_view.filters:
                from urllib.parse import urlencode
                return redirect(f"{request.path}?view={view}&{urlencode(saved_view.filters)}")
        

    table_key = f'project_list:{view}'
    layout_row = UserTableLayout.query.filter_by(user_id=user.id, table_key=table_key).first()
    saved_layout = layout_row.layout if layout_row else None

    deliverable_layout_row = UserTableLayout.query.filter_by(user_id=user.id, table_key='project_list:deliverable_table').first()
    saved_deliverable_layout = deliverable_layout_row.layout if deliverable_layout_row else None
    customer_layout_row = UserTableLayout.query.filter_by(user_id=user.id, table_key='project_list:customer_table').first()
    saved_customer_layout = customer_layout_row.layout if customer_layout_row else None
    
    query, order_by = _base_query_for_view(view, user)

    if query is None:
        projects = []
    else:
        query = _apply_sql_filters(query)
        projects = query.order_by(order_by).all()
    
    rows = [_serialize_row(p) for p in projects]
    rows = _apply_row_filters(rows)

    filter_counts = _build_filter_counts(view, user)

    view_total_query, _ = _base_query_for_view(view, user)
    view_total = view_total_query.count() if view_total_query is not None else 0

    filter_options = {
        'cs_leads': UserModel.query.filter(UserModel.role.in_(['cs', 'admin'])).order_by(UserModel.name).all(),
        'designers': UserModel.query.filter(UserModel.role.in_(['designer', 'team_lead'])).order_by(UserModel.name).all(),
        'clients': Client.query.order_by(Client.name).all(),
        'brief_types': [('standard', 'Standard'), ('ccm', 'C&CM')],
        'statuses': ['Not Started', 'Active', 'On Hold', 'Completed'],
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

    saved_views = ProjectTableView.query.filter_by(user_id=user.id).order_by(ProjectTableView.created_at).all()

    if view.startswith('view-'):
        try:
            current_view_row = ProjectTableView.query.filter_by(id=int(view[len('view-'):]), user_id=user.id).first()
        except ValueError:
            current_view_row = None
        current_base_view = current_view_row.base_view if current_view_row else 'my'
    else:
        current_base_view = view

    sort_field = request.args.get('sort', 'initial_deadline')
    if sort_field not in dict(SORT_FIELDS):
        sort_field = 'initial_deadline'

    sort_dir = request.args.get('dir', 'asc')
    if sort_dir not in ('asc', 'desc'):
        sort_dir = 'asc'

    group_field = request.args.get('group')
    if group_field not in dict(GROUP_FIELDS):
        group_field = None

    rows = _sort_rows(rows, sort_field, sort_dir)
    groups = _group_rows(rows, group_field) if group_field else None

    return render_template('project_list/index.html', rows=rows, view=view, effective_role=user.role, today=date.today(), filter_options=filter_options, 
                   active_filters=active_filters, filter_counts=filter_counts, view_total=view_total, table_key=table_key, saved_layout=saved_layout, active_filter_count=active_filter_count,
                   saved_deliverable_layout=saved_deliverable_layout, saved_customer_layout=saved_customer_layout, is_admin=(user.role == 'admin'), saved_views=saved_views, current_base_view=current_base_view,
                   sort_field=sort_field, sort_dir=sort_dir, group_field=group_field, groups=groups)

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

@project_list_bp.route('/views', methods=['POST'])
@login_required
def create_view():
    """ Saves one new named custom view: a name, which fixed preset it is built on top of to that preset,
        and  the current filter selection as a plain {param_name: value} dict - the exact shape a query
        string already has, so applying it back later uses urlencode() and a redirect, no reparsing needed"""

    user = _effective_user()
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    base_view = data.get('base_view')
    filters = data.get('filters') or {}

    if not name:
        return jsonify({'error': 'Name is required'}), 400
    if base_view not in ('my', 'all', 'approved'):
        return jsonify({'error': 'Invalid base view'}), 400

    view = ProjectTableView(user_id=user.id, name=name, base_view=base_view, filters=filters)
    db.session.add(view)
    db.session.commit()

    return jsonify({'id': view.id, 'url': url_for('project_list.index', view=f'view-{view.id}')})

@project_list_bp.route('/views/<int:view_id>/rename', methods=['POST'])
@login_required
def rename_view(view_id):
    user = _effective_user()
    view = ProjectTableView.query.filter_by(id=view_id, user_id=user.id).first()
    if not view:
        return jsonify({'error': 'View not found.'}), 404

    data = request.get_json(silent=True) or {}
    new_name = (data.get('name') or '').strip()
    if not new_name:
        return jsonify({'error': 'Name cannot be empty.'}), 400

    view.name = new_name
    db.session.commit()
    return jsonify({'success': True, 'name': view.name})


@project_list_bp.route('/views/<int:view_id>/delete', methods=['POST'])
@login_required
def delete_view(view_id):
    user = _effective_user()
    view = ProjectTableView.query.filter_by(id=view_id, user_id=user.id).first()
    if not view:
        return jsonify({'error': 'View not found.'}), 404

    db.session.delete(view)
    db.session.commit()
    return jsonify({'success': True})

@project_list_bp.route('/<int:project_id>/expand')
@login_required
def expand(project_id):
    project = Project.query.get_or_404(project_id)

    if project.brief_type == 'ccm':
        rows = []
        for pc in project.project_customers:
            if pc.cancelled:
                continue
            rows.append({
                'label': pc.customer.name,
                'design_deadline': pc.design_deadline,
                'installation_date': pc.installation_date,
                'deliverable_count': len(pc.deliverables),
                'revision_count': pc.posm_revision_count,
                'blanket_status': _blanket_status(pc.status),
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

def _blanket_status(granular_status):
    """ Maps the granular workflow states down to the following:
        Not Started / Active / On Hold / Completed / Archived.
    """

    if granular_status == 'draft':
        return 'Not Started'
    if granular_status == 'on_hold':
        return 'On Hold'
    if granular_status == 'approved':
        return 'Completed'
    return 'Active'

def _rollup_for(deliverable_query):
    """ The computed rollup: Shows how many of this projects deliverables are Approved out of the total."""

    deliverables = deliverable_query.all()
    total = len(deliverables)
    if total == 0:
        return None
    approved = sum(1 for d in deliverables if d.status == 'approved')
    return f'{approved} of {total} Approved'



