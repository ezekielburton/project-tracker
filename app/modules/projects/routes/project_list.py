# The Projects list page: one role-adaptive table, plus the endpoints for its
# filtering, sorting, row expansion and saved views.

from datetime import date
from flask import Blueprint, render_template, session, request, jsonify, url_for, redirect
from flask_login import login_required
from sqlalchemy import nullslast, func, case
from sqlalchemy.orm import joinedload, selectinload
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import Project, ProjectSecondaryCS, ProjectDesigner, Deliverable, User as UserModel, Client, UserTableLayout, ProjectCustomer, DesignType, ProjectTableView, ProjectStatusLog, ProjectPosmChannel, ActivityLog, ProjectNote, ProjectActivitySeen, DeliverableAssignment
from app.modules.core.shared.lib.status_vocabulary import derive_deliverable_status, derive_project_status, derive_customer_pipeline_status
from app.modules.core.shared.services.status_tracking import bulk_project_status_started_at, bulk_project_client_approved_at
from app.modules.core.shared.lib.capabilities import can, effective_user, require
from app.modules.core.shared.lib.utils import ACTIVITY_SEEN_ROLLOUT_CUTOFF

project_list_bp = Blueprint('project_list', __name__, url_prefix='/projects-new', template_folder='../templates')

def _serialize_person(u):
    """A user as {id, name, avatar_filename}, or None."""
    if not u:
        return None
    return {'id': u.id, 'name': u.name, 'avatar_filename': u.avatar_filename}

def _effective_user():
    """Emulation-aware actor (alias for effective_user())."""
    return effective_user()

def _eager_load(query):
    """Eager-load every relationship _serialize_row() touches, avoiding an N+1
    per row. Apply only where rows are serialized, not to .count() queries."""
    return query.options(
        joinedload(Project.cs_lead),
        joinedload(Project.project_owner),
        joinedload(Project.client_brand),
        selectinload(Project.assigned_designers).joinedload(ProjectDesigner.designer),
        selectinload(Project.project_customers),
    )


def _bulk_deliverable_aggregates(project_ids):
    """Deliverable rollup ("N of M Approved") and next deadline for many
    projects in one query each. Returns (rollups, next_deadlines) keyed by project_id."""
    if not project_ids:
        return {}, {}

    rollups = {}
    rollup_rows = (
        db.session.query(
            Deliverable.project_id,
            func.count(Deliverable.id),
            func.sum(case((Deliverable.status == 'approved', 1), else_=0)),
        )
        .filter(Deliverable.project_id.in_(project_ids))
        .group_by(Deliverable.project_id)
        .all()
    )
    for project_id, total, approved in rollup_rows:
        rollups[project_id] = f'{int(approved or 0)} of {total} Approved'

    # Next deadline: earliest design_deadline among non-Approved deliverables,
    # past dates included (overdue is the most urgent). The query is sorted
    # globally, so the first row seen per project is its earliest.
    next_deadlines = {}
    for d in (
        Deliverable.query
        .filter(Deliverable.project_id.in_(project_ids), Deliverable.status != 'approved')
        .order_by(nullslast(Deliverable.design_deadline), nullslast(Deliverable.design_deadline_time))
        .all()
    ):
        if d.project_id in next_deadlines or d.design_deadline is None:
            continue
        next_deadlines[d.project_id] = {'date': d.design_deadline, 'deliverable_name': d.name}

    return rollups, next_deadlines


def _bulk_activity_and_chat_at(project_ids):
    """For unread dots: latest update and chat time per project, one query each.
    Updates are ActivityLog rows with entity_type='project'; chats are ProjectNotes.
    Returns (last_update_at, last_chat_at) keyed by project_id; missing = none ever."""
    if not project_ids:
        return {}, {}

    last_update_at = dict(
        db.session.query(ActivityLog.entity_id, func.max(ActivityLog.created_at))
        .filter(ActivityLog.entity_type == 'project', ActivityLog.entity_id.in_(project_ids))
        .group_by(ActivityLog.entity_id)
        .all()
    )
    last_chat_at = dict(
        db.session.query(ProjectNote.project_id, func.max(ProjectNote.created_at))
        .filter(ProjectNote.project_id.in_(project_ids))
        .group_by(ProjectNote.project_id)
        .all()
    )
    return last_update_at, last_chat_at


def _bulk_activity_seen(project_ids, user):
    """This user's ProjectActivitySeen watermark rows, keyed by project_id.
    A missing key means no watermark yet (see _has_unread_activity)."""
    if not project_ids:
        return {}
    rows = (
        ProjectActivitySeen.query
        .filter(ProjectActivitySeen.user_id == user.id, ProjectActivitySeen.project_id.in_(project_ids))
        .all()
    )
    return {r.project_id: r for r in rows}


def _has_unread_activity(last_activity_at, seen_at):
    """True if the activity is newer than the watermark. With no watermark,
    ACTIVITY_SEEN_ROLLOUT_CUTOFF is the baseline; with no activity, never unread."""
    if last_activity_at is None:
        return False
    baseline = seen_at if seen_at is not None else ACTIVITY_SEEN_ROLLOUT_CUTOFF
    return last_activity_at > baseline


def _urgency_for(next_deadline, today):
    """Urgency bucket from days until next_deadline: overdue, urgent (today),
    prioritize (within 2 days) or normal. None if there is no deadline."""
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

# Design disciplines; must match the exact strings in User.team,
# DeliverableAssignment.team and Deliverable.teams.
TEAM_KEYS = ['2D', '3D', 'Technical']

def _team_columns_for(deliverable):
    """Per-team cell data for the sub-table: {'required', 'designer'} for each
    of TEAM_KEYS. Requested teams come from Deliverable.teams (CSV); the
    designer from DeliverableAssignment, so a team can be required but unassigned."""
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
    """One deliverable sub-table row. Used by both Standard and C&CM expansion."""
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
    """Parse a comma-separated query param of int IDs (e.g. ?cs_lead=3,7); [] if unset."""

    raw = request.args.get(param_name, '')
    if not raw:
        return []
    return [int(v) for v in raw.split(',') if v.strip().isdigit()]

def _parse_values(param_name):
    """Parse a comma-separated query param of strings (e.g. ?status=Briefed,On Hold)."""
    raw = request.args.get(param_name, '')
    if not raw:
        return []
    return [v for v in raw.split(',') if v]

def _parse_date(param_name):
    """Parse an ISO date query param; None if unset or invalid."""
    raw = request.args.get(param_name, '')
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None

def _row_passes_filters(row, exclude=None):
    """True if a serialized row matches every active filter except `exclude`.
    The single source of filter logic for _filter_rows and table_row()."""
    if exclude != 'cs_lead':
        cs_lead_ids = _parse_ids('cs_lead')
        if cs_lead_ids and not (row['cs_lead'] and row['cs_lead']['id'] in cs_lead_ids):
            return False

    if exclude != 'project_owner':
        owner_ids = _parse_ids('project_owner')
        if owner_ids and not (row['project_owner'] and row['project_owner']['id'] in owner_ids):
            return False

    if exclude != 'client':
        client_ids = _parse_ids('client')
        want_client_undefined = _has_undefined('client')
        if (client_ids or want_client_undefined) and not (
            (client_ids and row['client_id'] in client_ids)
            or (want_client_undefined and row['client_id'] is None)
        ):
            return False

    if exclude != 'brief_type':
        brief_types = _parse_values('brief_type')
        if brief_types and row['brief_type'] not in brief_types:
            return False

    if exclude != 'initial_deadline':
        initial_from = _parse_date('initial_deadline_from')
        if initial_from and not (row['initial_deadline'] and row['initial_deadline'] >= initial_from):
            return False

        initial_to = _parse_date('initial_deadline_to')
        if initial_to and not (row['initial_deadline'] and row['initial_deadline'] <= initial_to):
            return False

    if exclude != 'search':
        search = request.args.get('search', '').strip()
        if search:
            needle = search.lower()
            if not (needle in (row['name'] or '').lower() or needle in (row['job_number'] or '').lower()):
                return False

    if exclude != 'designers':
        designer_ids = _parse_ids('designers')
        want_undefined = _has_undefined('designers')
        if (designer_ids or want_undefined) and not (
            (designer_ids and any(d and d['id'] in designer_ids for d in row['designers']))
            or (want_undefined and not row['designers'])
        ):
            return False

    if exclude != 'status':
        statuses = _parse_values('status')
        if statuses and row['blanket_status'] not in statuses:
            return False

    if exclude != 'urgency':
        urgencies = _parse_values('urgency')
        if urgencies and row['urgency'] not in urgencies:
            return False

    if exclude != 'team':
        teams = _parse_values('team')
        want_undefined = _has_undefined('team')
        if (teams or want_undefined) and not (
            any(t in teams for t in row['design_teams'])
            or (want_undefined and not _has_known_team(row))
        ):
            return False

    if exclude != 'design_type':
        design_types = _parse_values('design_type')
        want_undefined = _has_undefined('design_type')
        if (design_types or want_undefined) and not (
            row['design_type'] in design_types
            or (want_undefined and row['design_type'] is None)
        ):
            return False

    if exclude != 'next_deadline':
        next_from = _parse_date('next_deadline_from')
        if next_from and not (row['next_deadline'] and row['next_deadline']['date'] >= next_from):
            return False

        next_to = _parse_date('next_deadline_to')
        if next_to and not (row['next_deadline'] and row['next_deadline']['date'] <= next_to):
            return False

    return True


def _filter_rows(rows, exclude=None):
    """Rows matching every active filter except `exclude`. Excluding a
    dimension lets its own option counts ignore its current selection."""
    return [r for r in rows if _row_passes_filters(r, exclude)]

def _resolve_view(view, user):
    """Resolve a saved view ("view-<id>") to its base preset ('my', 'all' or
    'design_complete'); falls back to 'my'. Presets pass through unchanged."""
    if view.startswith('view-'):
        try:
            view_id = int(view.split('-', 1)[1])
        except ValueError:
            view_id = None
        saved_view = ProjectTableView.query.filter_by(id=view_id, user_id=user.id).first() if view_id else None
        return saved_view.base_view if saved_view else 'my'
    return view


def _base_query_for_view(view, user):
    """(query, order_by) for the active preset view, before filters. Also
    scopes the filter option counts to the view."""
    order_by = Project.first_output_deadline.asc()
    view = _resolve_view(view, user)

    # Raw 'approved' (shown as Pre-Production) is still in flight, so My/All
    # exclude only the terminal 'handed_to_production', matching the
    # dashboard's scope_query().
    if view == 'all':
        if can('view_all_projects', user):
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
        # Design Complete tab: projects handed to production, plus C&CM
        # projects with any channel approved or handed over. Newest handover
        # first, taken from the status log (no timestamp column on Project).
        handed_at = (
            db.session.query(db.func.max(ProjectStatusLog.started_at))
            .filter(
                ProjectStatusLog.project_id == Project.id,
                ProjectStatusLog.status == 'handed_to_production'
            )
            .correlate(Project)
            .scalar_subquery()
        )
        query = Project.query.filter(
            db.or_(
                Project.project_status == 'handed_to_production',
                db.and_(
                    Project.brief_type == 'ccm',
                    Project.posm_channels.any(ProjectPosmChannel.status.in_(('approved', 'handed_to_production')))
                )
            )
        )
        order_by = handed_at.desc()

    else:  # 'my' - default
        if can('view_all_projects', user):
            # My Projects: projects the user leads, is secondary CS on, or
            # owns, for every role here, admin included. 'all' shows the rest.
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

    # Cancelled projects are hidden unless the Cancelled status is selected
    # (_show_cancelled). Applied once here so every view and count agrees.
    if query is not None and not _show_cancelled():
        query = query.filter(Project.cancelled_at.is_(None))

    return query, order_by

# Safety cap so a view can't serialize thousands of projects per request or
# SSE ping. Fetched as cap+1 to detect truncation without a COUNT query.
_VIEW_ROW_CAP = 500

def _fetch_all_view_rows(view, user):
    """The single DB fetch per request: every project in the view, serialized,
    before filters. Callers filter, sort, group and count this list in memory.
    Capped at _VIEW_ROW_CAP; returns (rows, truncated) so callers can warn."""
    query, order_by = _base_query_for_view(view, user)
    if query is None:
        return [], False

    projects = _eager_load(query).order_by(order_by).limit(_VIEW_ROW_CAP + 1).all()
    truncated = len(projects) > _VIEW_ROW_CAP
    if truncated:
        projects = projects[:_VIEW_ROW_CAP]
    project_ids = [p.id for p in projects]
    rollups, next_deadlines = _bulk_deliverable_aggregates(project_ids)
    status_started_at = bulk_project_status_started_at(project_ids)
    client_approved_at = bulk_project_client_approved_at(project_ids)
    # Unread dots.
    last_update_at, last_chat_at = _bulk_activity_and_chat_at(project_ids)
    seen_by_project = _bulk_activity_seen(project_ids, user)
    rows = [
        _serialize_row(p, rollups, next_deadlines, status_started_at, client_approved_at,
                       last_update_at, last_chat_at, seen_by_project)
        for p in projects
    ]
    return rows, truncated


def _rows_excluding(all_rows, exclude):
    """Rows matching every active filter except `exclude`, for that filter's
    own option counts."""
    return _filter_rows(all_rows, exclude=exclude)

def _count_by_id(rows, key):
    """Count rows by a single-person field (e.g. 'cs_lead'), keyed by user id."""
    counts = {}
    for r in rows:
        person = r[key]
        if person:
            counts[person['id']] = counts.get(person['id'], 0) + 1
    return counts

def _count_by_id_list(rows, key):
    """Count rows by a list-of-people field; a row counts toward each person."""
    counts = {}
    for r in rows:
        for person in r[key]:
            if person:
                counts[person['id']] = counts.get(person['id'], 0) + 1
    return counts

def _count_by_value(rows, key):
    """Count rows by a scalar field (e.g. client_id, blanket_status), skipping None."""
    counts = {}
    for r in rows:
        value = r[key]
        if value is not None:
            counts[value] = counts.get(value, 0) + 1
    return counts

def _show_cancelled():
    """True if ?status includes Cancelled, the only way cancelled projects
    enter a view. The Show Cancelled button just sets that filter."""
    return 'Cancelled' in _parse_values('status')

def _has_undefined(param_name):
    """True if a filter param includes the admin-only 'undefined' sentinel
    (e.g. ?client=3,undefined). _parse_ids drops it, so it's checked here."""
    raw = request.args.get(param_name, '')
    return 'undefined' in [v.strip() for v in raw.split(',') if v.strip()]

def _has_known_team(row):
    """True if the row requests at least one of TEAM_KEYS. Rows without one
    are "Undefined" in the Team filter, its count and the team grouping."""
    return any(t in TEAM_KEYS for t in row['design_teams'])

def _count_undefined(rows, key):
    """Count rows where the field is empty (None or []). Callers store it
    under the None key, which the template reads for the Undefined chip."""
    return sum(1 for r in rows if not r[key])

def _count_by_list_membership(rows, key):
    """Count rows by each string in a list field (e.g. 'design_teams')."""
    counts = {}
    for r in rows:
        for value in r[key]:
            counts[value] = counts.get(value, 0) + 1
    return counts


def _build_filter_counts(all_rows):
    """Live count for every filter option, scoped to the view plus every
    other active filter. All in-memory over _fetch_all_view_rows()'s list."""
    client_rows = _rows_excluding(all_rows, 'client')
    designer_rows = _rows_excluding(all_rows, 'designers')
    design_type_rows = _rows_excluding(all_rows, 'design_type')

    client_counts = _count_by_value(client_rows, 'client_id')
    client_counts[None] = _count_undefined(client_rows, 'client_id')

    designer_counts = _count_by_id_list(designer_rows, 'designers')
    designer_counts[None] = _count_undefined(designer_rows, 'designers')

    design_type_counts = _count_by_value(design_type_rows, 'design_type')
    design_type_counts[None] = _count_undefined(design_type_rows, 'design_type')

    team_rows = _rows_excluding(all_rows, 'team')
    team_counts = _count_by_list_membership(team_rows, 'design_teams')
    team_counts[None] = sum(1 for r in team_rows if not _has_known_team(r))

    return {
        'cs_lead': _count_by_id(_rows_excluding(all_rows, 'cs_lead'), 'cs_lead'),
        'project_owner': _count_by_id(_rows_excluding(all_rows, 'project_owner'), 'project_owner'),
        'designers': designer_counts,
        'client': client_counts,
        'brief_type': _count_by_value(_rows_excluding(all_rows, 'brief_type'), 'brief_type'),
        'status': _count_by_value(_rows_excluding(all_rows, 'status'), 'blanket_status'),
        'urgency': _count_by_value(_rows_excluding(all_rows, 'urgency'), 'urgency'),
        'team': team_counts,
        'design_type': design_type_counts,
    }

def _serialize_row(p, rollups, next_deadlines, status_started_at=None, client_approved_at=None,
                   last_update_at=None, last_chat_at=None, seen_by_project=None):
    """Turn one Project into the flat row dict the template needs. The other
    args are per-project dicts from the _bulk_* helpers; the optional ones
    default to None (their fields come out None/False)."""
    next_deadline = next_deadlines.get(p.id)
    status_label, status_class = derive_project_status(p)
    seen = (seen_by_project or {}).get(p.id)
    return {
        'id': p.id,
        'name': p.name,
        'client': p.client_brand.name if p.client_brand else None,
        'client_id': p.client_id,
        'job_number': p.job_number,
        'cs_lead': _serialize_person(p.cs_lead),
        'project_owner': _serialize_person(p.project_owner),
        'designers': [_serialize_person(pd.designer) for pd in p.assigned_designers],
        'design_teams': [t.strip() for t in (p.design_teams_requested or '').split(',') if t.strip()],
        'design_type': 'ccm' if p.brief_type == 'ccm' else (str(p.design_type_id) if p.design_type_id else None),
        'initial_deadline': p.first_output_deadline,
        'status': p.project_status,
        'blanket_status': status_label,
        'status_pill_class': status_class,
        # When the raw status last changed (ProjectStatusLog); None if unknown.
        'status_started_at': (status_started_at or {}).get(p.id),
        # When the client approved; kept after the project moves on. None if never.
        'client_approved_at': (client_approved_at or {}).get(p.id),
        'brief_type': p.brief_type,
        'rollup': rollups.get(p.id),
        'customer_count': sum(1 for pc in p.project_customers if not pc.cancelled) if p.brief_type == 'ccm' else None,
        'next_deadline': next_deadline,
        'urgency': _urgency_for(next_deadline, date.today()),
        # Two independent unread dots: a row can show either, both, or neither.
        'has_unread_update': _has_unread_activity(
            (last_update_at or {}).get(p.id), seen.last_seen_update_at if seen else None),
        'has_unread_chat': _has_unread_activity(
            (last_chat_at or {}).get(p.id), seen.last_seen_chat_at if seen else None),
    }

def _compute_rows_and_groups(all_rows):
    """Filter, sort, then group the view's rows. Shared by the page and the
    live-refresh endpoint so they can't drift."""
    rows = _filter_rows(all_rows)

    sort_field = request.args.get('sort', '')
    sort_dir = request.args.get('dir', 'asc') if sort_field else ''
    if sort_field in SORT_FIELDS:
        rows = _sort_rows(rows, sort_field, sort_dir)
    else:
        # Unknown ?sort= value: keep the view's default order.
        sort_field = ''
        sort_dir = ''

    # Grouping buckets the already-sorted rows; order within a group is kept.
    group_field = request.args.get('group', '')
    if group_field in dict(GROUP_FIELDS):
        groups = _group_rows(rows, group_field)
    else:
        group_field = ''
        groups = None

    return rows, groups, sort_field, sort_dir, group_field


@project_list_bp.route('/table-rows')
@login_required
@require('view_workspace')
def table_rows():
    """Full table refresh: the client re-fetches this on an SSE ping and swaps
    it into #project-table. Must not write session['last_project_view']."""
    user = _effective_user()
    view = request.args.get('view') or session.get('last_project_view', 'my')
    all_rows, _truncated = _fetch_all_view_rows(view, user)
    rows, groups, sort_field, sort_dir, group_field = _compute_rows_and_groups(all_rows)
    return render_template('project_list/_table_rows.html', rows=rows, groups=groups, today=date.today())


@project_list_bp.route('/table-rows/<int:project_id>')
@login_required
@require('view_workspace')
def table_row(project_id):
    """Single-row refresh, using the same view query and filter check as the
    full list. 204 means the project is out of the view/filter, and
    project_list.js removes the row."""
    user = _effective_user()
    view = request.args.get('view') or session.get('last_project_view', 'my')
    query, _order_by = _base_query_for_view(view, user)
    if query is None:
        return '', 204

    project = _eager_load(query).filter(Project.id == project_id).first()
    if project is None:
        return '', 204

    rollups, next_deadlines = _bulk_deliverable_aggregates([project_id])
    status_started_at = bulk_project_status_started_at([project_id])
    client_approved_at = bulk_project_client_approved_at([project_id])
    last_update_at, last_chat_at = _bulk_activity_and_chat_at([project_id])
    seen_by_project = _bulk_activity_seen([project_id], user)
    row = _serialize_row(project, rollups, next_deadlines, status_started_at, client_approved_at,
                          last_update_at, last_chat_at, seen_by_project)

    if not _row_passes_filters(row):
        return '', 204
    return render_template('project_list/_single_row.html', row=row, today=date.today())


def _redirect_target_for_fresh_saved_view(view, user):
    """On a fresh landing on a saved view (no args beyond ?view), return the params
    to redirect to so its saved filters become real query args; else None.
    Used by index() and page_state(); fetch() follows the redirect."""
    if not (view.startswith('view-') and len(request.args) <= 1):
        return None
    try:
        view_id = int(view.split('-', 1)[1])
    except ValueError:
        return None
    saved_view = ProjectTableView.query.filter_by(id=view_id, user_id=user.id).first() if view_id else None
    if saved_view is None or not saved_view.filters:
        return None
    params = dict(saved_view.filters)
    params['view'] = view
    return params


def _build_page_context(view, user):
    """Template context for the page: `view` plus the request's filter, sort,
    group and search args. Shared by index() and page_state() so they match."""
    table_key = f'project_list:{view}'

    layout_row = UserTableLayout.query.filter_by(user_id=user.id, table_key=table_key).first()
    saved_layout = layout_row.layout if layout_row else None

    deliverable_layout_row = UserTableLayout.query.filter_by(user_id=user.id, table_key='project_list:deliverable_table').first()
    saved_deliverable_layout = deliverable_layout_row.layout if deliverable_layout_row else None
    customer_layout_row = UserTableLayout.query.filter_by(user_id=user.id, table_key='project_list:customer_table').first()
    saved_customer_layout = customer_layout_row.layout if customer_layout_row else None
    
    # One fetch; rows and filter counts are both computed from it in memory.
    all_rows, view_capped = _fetch_all_view_rows(view, user)
    rows, groups, sort_field, sort_dir, group_field = _compute_rows_and_groups(all_rows)

    filter_counts = _build_filter_counts(all_rows)

    view_total_query, _ = _base_query_for_view(view, user)
    view_total = view_total_query.count() if view_total_query is not None else 0

    filter_options = {
        # Deactivated people stay selectable (projects still reference them), sorted last.
        'cs_leads': UserModel.query.filter(UserModel.role.in_(['cs', 'admin'])).order_by(UserModel.is_active.desc(), UserModel.name).all(),
        'designers': UserModel.query.filter(UserModel.role.in_(['designer', 'team_lead'])).order_by(UserModel.is_active.desc(), UserModel.name).all(),
        'project_owners': UserModel.query.filter_by(role='project_owner').order_by(UserModel.is_active.desc(), UserModel.name).all(),
        'clients': Client.query.order_by(Client.name).all(),
        'brief_types': [('standard', 'Standard'), ('ccm', 'C&CM')],
        # Must match derive_project_status labels (status_vocabulary.py).
        'statuses': [
            'Briefed', 'In Design', 'Pre-Production', 'Handed to Production', 'On Hold', 'Cancelled',
        ],
        'urgencies': [('overdue', 'Overdue'), ('urgent', 'Urgent'), ('prioritize', 'Prioritize'), ('normal', 'Normal')],
        'teams': TEAM_KEYS,
        'design_types': [('ccm', 'C&CM')] + [(str(dt.id), dt.name) for dt in DesignType.query.order_by(DesignType.name).all()],
    }

    active_filters = {
        'cs_lead': _parse_ids('cs_lead'),
        'project_owner': _parse_ids('project_owner'),
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
        bool(active_filters['project_owner']),
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

    # Saved-view tabs, and the preset the active view is built on (submitted
    # as `base_view` by the "Save as new view" popover).
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

    # Dirty = current filters/sort/group differ from the saved view's. Column
    # layout is excluded; it is saved separately.
    current_params = {k: v for k, v in request.args.items() if k!= 'view' and v}
    baseline_params = dict(active_saved_view.filters) if active_saved_view and active_saved_view.filters else {}
    is_dirty = current_params != baseline_params

    return dict(rows=rows, view=view, effective_role=user.role, today=date.today(), filter_options=filter_options,
                       active_filters=active_filters, filter_counts=filter_counts, view_total=view_total, table_key=table_key, saved_layout=saved_layout, active_filter_count=active_filter_count,
                       saved_deliverable_layout=saved_deliverable_layout, saved_customer_layout=saved_customer_layout, is_admin=can('override_status', user),
                       sort_options=SORT_OPTIONS, sort_field=sort_field, sort_dir=sort_dir,
                       saved_views=saved_views, current_base_view=current_base_view, is_dirty=is_dirty,
                       group_options=GROUP_FIELDS, group_field=group_field, groups=groups, show_cancelled=_show_cancelled(),
                       view_capped=view_capped, view_row_cap=_VIEW_ROW_CAP, )


@project_list_bp.route('/')
@login_required
@require('view_workspace')
def index():
    """The Projects list page for the requested (or last-used) view."""
    user = _effective_user()
    # Remember the last tab (per session) since the sidebar link has no query string.
    view = request.args.get('view')
    if view:
        session['last_project_view'] = view
    else:
        view = session.get('last_project_view', 'my')

    redirect_params = _redirect_target_for_fresh_saved_view(view, user)
    if redirect_params is not None:
        return redirect(url_for('project_list.index', **redirect_params))

    context = _build_page_context(view, user)
    return render_template('project_list/index.html', **context)


@project_list_bp.route('/page-state')
@login_required
@require('view_workspace')
def page_state():
    """JSON version of index() for softNavigate() in project_list.js: rendered
    fragments plus the scalars index.html's inline script sets. Saved views
    redirect back here; the client reads response.url for the address bar.
    Must not write session['last_project_view']."""
    user = _effective_user()
    view = request.args.get('view') or session.get('last_project_view', 'my')

    redirect_params = _redirect_target_for_fresh_saved_view(view, user)
    if redirect_params is not None:
        return redirect(url_for('project_list.page_state', **redirect_params))

    context = _build_page_context(view, user)
    sort_field = context['sort_field']
    group_field = context['group_field']
    sort_badge_count = 2 if (sort_field and group_field) else (1 if (sort_field or group_field) else 0)

    return jsonify({
        'view': context['view'],
        'tab_strip_html': render_template('project_list/_tab_strip.html', **context),
        'filter_panel_html': render_template('project_list/_filter_panel_body.html', **context),
        'sort_panel_html': render_template('project_list/_sort_panel_body.html', **context),
        'table_html': render_template('project_list/_table_rows.html', rows=context['rows'], groups=context['groups'], today=context['today']),
        'table_key': context['table_key'],
        'saved_layout': context['saved_layout'],
        'saved_deliverable_layout': context['saved_deliverable_layout'],
        'saved_customer_layout': context['saved_customer_layout'],
        'current_base_view': context['current_base_view'],
        'is_dirty': context['is_dirty'],
        'groups': bool(context['groups']),
        'active_filter_count': context['active_filter_count'],
        'sort_badge_count': sort_badge_count,
        'show_cancelled': context['show_cancelled'],
        'search': context['active_filters']['search'],
        'view_total': context['view_total'],
        'shown_count': len(context['rows']),
    })


@project_list_bp.route('/layout', methods=['POST'])
@login_required
@require('view_workspace')
def save_layout():
    """Save the user's column widths/order for one table key (debounced client-side)."""
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
@require('view_workspace')
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

    deliverables = Deliverable.query.filter_by(project_id=project.id).options(
        selectinload(Deliverable.disciplines).joinedload(DeliverableAssignment.designer)
    ).order_by(Deliverable.id).all()
    rows = [_serialize_deliverable_row(d) for d in deliverables]
    return render_template('project_list/_deliverable_table.html', rows=rows, today=date.today(), brief_type='standard')

@project_list_bp.route('/customer/<int:project_customer_id>/expand')
@login_required
@require('view_workspace')
def expand_customer(project_customer_id):
    """C&CM second level: one customer's deliverables, fetched on expand."""
    pc = ProjectCustomer.query.get_or_404(project_customer_id)
    deliverables = Deliverable.query.filter_by(project_customer_id=pc.id).options(
        selectinload(Deliverable.disciplines).joinedload(DeliverableAssignment.designer)
    ).order_by(Deliverable.id).all()
    rows = [_serialize_deliverable_row(d) for d in deliverables]
    return render_template('project_list/_deliverable_table.html', rows=rows, today=date.today(), brief_type='ccm')

# ---- Sorting ----
# Sort popout options as (value, label), in display order.
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

# Most urgent first. No urgency (no next deadline) gets 4, so it sorts last.
_URGENCY_SORT_ORDER = {'overdue': 0, 'urgent': 1, 'prioritize': 2, 'normal': 3}

# Key functions (row, reverse) -> sort value. The date fields swap their
# missing-date sentinel on reverse so undated rows stay last either way.
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
    """Sort rows in Python; several sort fields (urgency, next_deadline) are
    computed, not SQL columns."""
    key_fn = SORT_FIELDS.get(field)
    if key_fn is None:
        return rows
    reverse = direction == 'desc'
    return sorted(rows, key=lambda r: key_fn(r, reverse), reverse=reverse)


# ---- Grouping ----
# Group-by options as (value, label), in display order. Sort runs first.
GROUP_FIELDS = [
    ('cs_lead', 'CS Lead'),
    ('client', 'Client'),
    ('team', 'Team'),
    ('urgency', 'Urgency'),
    ('status', 'Status'),
    ('next_deadline_month', 'Month'),
]

def _group_key_and_label(row, field):
    """(sort_key, label) for single-value group fields. `team` is multi-value
    and handled in _group_rows."""
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
    if field == 'next_deadline_month':
        # Month of next_deadline, chronological; rows without one go in a
        # trailing "No Deadline" group.
        next_deadline = row['next_deadline']
        if next_deadline:
            d = next_deadline['date']
            return ((0, d.year, d.month), d.strftime('%B %Y'))
        return ((1, 0, 0), 'No Deadline')
    return None

def _group_rows(rows, field):
    """Bucket sorted rows into [{'key', 'label', 'rows'}] in display order,
    keeping row order within each group. `team` follows TEAM_KEYS order, a
    row appears in every team it requests, and teamless rows go to Undefined."""
    if field == 'team':
        buckets = {team: [] for team in TEAM_KEYS}
        undefined_bucket = []
        for row in rows:
            # Only TEAM_KEYS get a group, so a row with no recognised team
            # goes to Undefined rather than vanishing from the list.
            teams = [t for t in row['design_teams'] if t in buckets]
            if not teams:
                undefined_bucket.append(row)
                continue
            for team in teams:
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
@require('view_workspace')
def create_view():
    """Save the current filters as a named tab on a preset. Body: name,
    base_view (the active preset) and filters (query params minus `view`)."""
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
@require('view_workspace')
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
@require('view_workspace')
def delete_view(view_id):
    user = _effective_user()
    view = ProjectTableView.query.filter_by(id=view_id, user_id=user.id).first_or_404()
    db.session.delete(view)
    db.session.commit()
    return jsonify({'status': 'ok'})

