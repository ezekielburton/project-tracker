"""
Client Servicing table — the read view. Every row is a Project, with its
CS extension row (if one exists yet) joined in. Field writes live in
edit.py, on the same blueprint.
"""
from datetime import date

from flask import render_template, abort
from flask_login import login_required
from sqlalchemy.orm import joinedload, selectinload

from app.modules.core.shared.models import Project, ProjectDesigner, Contact, UserTableLayout
from app.modules.core.shared.lib.users import active_users
from app.modules.core.shared.lib.status_vocabulary import derive_project_status
from app.modules.core.shared.services.status_tracking import bulk_project_client_approved_at

from app.modules.client_servicing.models import ClientServicing, ClientServicingScope
from app.modules.client_servicing.lib.access import can_access_client_servicing, _effective_user
from app.modules.client_servicing.routes.blueprint import client_servicing_bp


def _require_access():
    if not can_access_client_servicing(_effective_user()):
        abort(403)


# Every reorderable/resizable column, in the default order — key must
# match a macro name in _columns.html ("cell_" + key) and, for editable
# columns, the data-field the edit endpoint expects. The pinned "Open in
# Projects" column isn't here: it's not reorderable or resizable, same as
# the Projects page's own Expand column.
COLUMNS = [
    {'key': 'client', 'label': 'Client'},
    {'key': 'project', 'label': 'Project'},
    {'key': 'brief_date', 'label': 'Brief Date'},
    {'key': 'designers', 'label': 'Lead Designer(s)'},
    {'key': 'client_approval', 'label': 'Client Approval'},
    {'key': 'status', 'label': 'Status'},
    {'key': 'job_number', 'label': 'Job No'},
    {'key': 'cs_lead', 'label': 'CS Contact'},
    {'key': 'project_owner', 'label': 'Project Owner'},
    {'key': 'client_spoc', 'label': 'Client SPOC'},
    {'key': 'installation_date', 'label': 'Installation Date'},
    {'key': 'value', 'label': 'Project Value (AED)'},
    {'key': 'due_date', 'label': 'Due Date'},
    {'key': 'scope', 'label': 'Scope'},
    {'key': 'lpo', 'label': 'LPO'},
    {'key': 'store_location', 'label': 'Store / Location'},
    {'key': 'removal_date', 'label': 'Removal Date'},
    {'key': 'invoice_month', 'label': 'Invoice Month'},
    {'key': 'cost_to_client', 'label': 'Cost to Client (AED)'},
    {'key': 'inward_cost', 'label': 'Inward Cost (AED)'},
    {'key': 'margin_percent', 'label': 'Margin %'},
    {'key': 'priority', 'label': 'Priority'},
]

# One row per (user, TABLE_KEY) in the shared UserTableLayout model — same
# table_key convention the Projects page already uses for its own tables
# ('project_list:my', etc.), just this module's own key. Stores column
# widths; the array order also drives column order once reorder writes to it.
TABLE_KEY = 'client_servicing:table'


def _saved_layout():
    """The effective user's raw saved layout array for this table — a
    list of {'key': ..., 'width': ...} dicts in display order — or [] if
    they've never resized/reordered anything. Fetched once per request
    and shared by _ordered_columns() and _column_widths() below so a
    page load only queries UserTableLayout a single time.

    Keyed on _effective_user(), not current_user — an admin previewing
    the page while emulating someone else should see (and, via
    layout.py's save_layout, persist) THAT person's own saved column
    layout, same as project_list.py does for its own tables."""
    row = UserTableLayout.query.filter_by(user_id=_effective_user().id, table_key=TABLE_KEY).first()
    if not row or not row.layout:
        return []
    return [entry for entry in row.layout if isinstance(entry, dict) and entry.get('key')]


def _ordered_columns(saved):
    """COLUMNS reordered to match the user's saved key order. A saved key
    that no longer exists in COLUMNS (e.g. after a schema change) is
    silently ignored; a COLUMNS key missing from the saved layout (a
    column added since the user last dragged anything, or a first-ever
    visit) is appended at the end in its default position — so nobody
    ever loses a column to a stale or incomplete save.

    Project is then forced back to the very front (right after the
    pinned "Open in Projects" column, which isn't in COLUMNS at all) even
    if a saved layout has it somewhere else — it's a sticky, pinned
    column on the page (client_servicing.js excludes it from the
    reorder-drag entirely, same as the Projects page pins its own Name
    column), so the rendered order has to guarantee it's always first,
    not just usually first."""
    by_key = {col['key']: col for col in COLUMNS}
    saved_keys = [entry['key'] for entry in saved if entry['key'] in by_key]
    ordered = [by_key[key] for key in saved_keys]
    remaining_keys = set(saved_keys)
    ordered += [col for col in COLUMNS if col['key'] not in remaining_keys]

    project_index = next((i for i, col in enumerate(ordered) if col['key'] == 'project'), None)
    if project_index is not None and project_index != 0:
        ordered.insert(0, ordered.pop(project_index))
    return ordered


def _column_widths(saved):
    """{column_key: saved_width_px} for the current user, or {} if
    they've never resized anything — every column just falls back to its
    normal content-based width in that case."""
    return {
        entry.get('key'): entry.get('width')
        for entry in saved
        if entry.get('width')
    }


def _serialize_person(user):
    if not user:
        return None
    return {'id': user.id, 'name': user.name, 'avatar_filename': user.avatar_filename}


def _eager_load(query):
    """Bulk-loads every relationship the row serializer touches, so
    listing every project doesn't fire one query per row per
    relationship — same reasoning as project_list.py's _eager_load."""
    return query.options(
        joinedload(Project.cs_lead),
        joinedload(Project.project_owner),
        joinedload(Project.client_brand),
        selectinload(Project.assigned_designers).joinedload(ProjectDesigner.designer),
        joinedload(Project.client_servicing).joinedload(ClientServicing.scope),
    )


def _serialize_row(p, contacts_by_id, client_approved_at):
    cs = p.client_servicing
    contact = contacts_by_id.get(p.contact_id) if p.contact_id else None
    status_label, status_class = derive_project_status(p)
    designers = [_serialize_person(pd.designer) for pd in p.assigned_designers]
    return {
        'id': p.id,
        'client_id': p.client_id,
        'client': p.client_brand.name if p.client_brand else None,
        'name': p.name,
        'briefing_date': p.briefing_date,
        'designers': designers,
        # Comma-joined names: click-to-sort needs one flat sortable string
        # per column, and designers is the only list-valued column.
        # Computed here so the sort value and the chips can't drift.
        'designers_sort': ', '.join(d['name'] for d in designers if d),
        'client_approved_at': client_approved_at.get(p.id),
        'status_label': status_label,
        'status_class': status_class,
        'job_number': p.job_number,
        'contact_id': p.contact_id,
        'cs_lead': _serialize_person(p.cs_lead),
        'project_owner': _serialize_person(p.project_owner),
        'client_spoc': contact.name if contact else None,
        'installation_date': p.installation_date,
        'value': p.value,
        'due_date': p.first_output_deadline,
        'scope': cs.scope.name if (cs and cs.scope) else None,
        'scope_id': cs.scope_id if cs else None,
        'lpo': cs.lpo if cs else None,
        'store_location': cs.store_location if cs else None,
        'removal_date': cs.removal_date if cs else None,
        'invoice_month': cs.invoice_month if cs else None,
        'cost_to_client': cs.cost_to_client if cs else None,
        'inward_cost': cs.inward_cost if cs else None,
        'margin_percent': cs.margin_percent if cs else None,
        'priority': cs.priority if cs else None,
    }


def _scope_options():
    return [
        {'id': s.id, 'name': s.name}
        for s in ClientServicingScope.query.filter_by(active=True).order_by(ClientServicingScope.name).all()
    ]


def _person_options(role):
    return [{'id': u.id, 'name': u.name} for u in active_users(role)]


def _contacts_by_client(client_ids):
    if not client_ids:
        return {}
    by_client = {}
    for c in Contact.query.filter(Contact.client_id.in_(client_ids)).order_by(Contact.name).all():
        by_client.setdefault(c.client_id, []).append({'id': c.id, 'name': c.name})
    return by_client


def _base_projects():
    """The projects the CS module lists — drafts excluded (a draft isn't a
    real project yet). Shared by the table and the Invoicing tab."""
    return _eager_load(Project.query).filter(Project.project_status != 'draft')


def _page_context():
    """Everything a template needs: the rows, plus every dropdown's
    option list. scope/cs-lead/project-owner options are global; contact
    options are keyed by client_id since Client SPOC's choices are
    whichever client that row's project belongs to."""
    projects = _base_projects().order_by(Project.name.asc()).all()

    contact_ids = {p.contact_id for p in projects if p.contact_id}
    contacts_by_id = (
        {c.id: c for c in Contact.query.filter(Contact.id.in_(contact_ids))}
        if contact_ids else {}
    )
    client_approved_at = bulk_project_client_approved_at([p.id for p in projects])
    rows = [_serialize_row(p, contacts_by_id, client_approved_at) for p in projects]

    client_ids = {p.client_id for p in projects if p.client_id}
    saved = _saved_layout()
    return {
        'rows': rows,
        'today': date.today(),
        'columns': _ordered_columns(saved),
        'table_key': TABLE_KEY,
        'column_widths': _column_widths(saved),
        'scope_options': _scope_options(),
        'cs_lead_options': _person_options('cs'),
        'project_owner_options': _person_options('project_owner'),
        'contacts_by_client': _contacts_by_client(client_ids),
    }


@client_servicing_bp.route('/')
@login_required
def index():
    _require_access()
    return render_template('client_servicing/index.html', **_page_context())


@client_servicing_bp.route('/table-rows')
@login_required
def table_rows():
    """Full-refresh endpoint. The SSE ping handler (client_servicing.js)
    re-fetches this and swaps it into #client-servicing-table-body —
    same pattern as the Projects page's table_rows()."""
    _require_access()
    return render_template('client_servicing/_table_rows.html', **_page_context())
