"""
Client Servicing table — the read view. Every row is a Project joined to
its ClientServicing row, if it has one. Field writes live in edit.py.
"""
from datetime import date

from flask import render_template
from flask_login import login_required
from sqlalchemy.orm import joinedload, selectinload

from app.modules.core.shared.models import Project, ProjectDesigner, Contact, UserTableLayout
from app.modules.core.shared.lib.users import active_users
from app.modules.core.shared.services.status_tracking import bulk_project_client_approved_at

from app.modules.client_servicing.models import ClientServicing, ClientServicingScope
from app.modules.client_servicing.lib.status import (
    effective_cs_status, cs_design_indicator, CS_STATUS_OPTIONS,
)
from app.modules.core.shared.lib.capabilities import effective_user
from app.modules.client_servicing.lib.access import can_close_projects, require_cs
from app.modules.client_servicing.routes.blueprint import client_servicing_bp


# Every reorderable/resizable column, in default order. key must match a
# macro in _columns.html ("cell_" + key) and, for editable columns, the
# data-field edit.py expects. The pinned "Open in Projects" column is not
# listed because it cannot be moved or resized.
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

# UserTableLayout key for this table (one row per user). The saved list
# holds column widths, and its order is the column order. layout.py uses it.
TABLE_KEY = 'client_servicing:table'


def _saved_layout():
    """The effective user's saved layout ([] if none). Emulation-aware, so an
    admin previewing as someone sees that person's layout."""
    row = UserTableLayout.query.filter_by(user_id=effective_user().id, table_key=TABLE_KEY).first()
    if not row or not row.layout:
        return []
    return [entry for entry in row.layout if isinstance(entry, dict) and entry.get('key')]


def _ordered_columns(saved):
    """COLUMNS in the user's saved order. Unknown saved keys are dropped and
    unsaved columns appended. Project is forced first: it is the pinned
    sticky column."""
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
    """{column_key: width_px} from the saved layout. Unsaved columns use
    their content-based width."""
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
    """Bulk-loads every relationship the row serializer touches, to avoid
    N+1 queries. lib/calendar.py relies on these being loaded too."""
    return query.options(
        joinedload(Project.cs_lead),
        joinedload(Project.project_owner),
        joinedload(Project.client_brand),
        selectinload(Project.assigned_designers).joinedload(ProjectDesigner.designer),
        joinedload(Project.client_servicing).joinedload(ClientServicing.scope),
        selectinload(Project.project_deliverables),
    )


def _serialize_row(p, contacts_by_id, client_approved_at):
    cs = p.client_servicing
    contact = contacts_by_id.get(p.contact_id) if p.contact_id else None
    status_label, status_class, status_is_auto = effective_cs_status(p)
    status_indicators = cs_design_indicator(p) if (status_is_auto and status_label == 'In Design') else []
    designers = [_serialize_person(pd.designer) for pd in p.assigned_designers]
    return {
        'id': p.id,
        'client_id': p.client_id,
        'client': p.client_brand.name if p.client_brand else None,
        'name': p.name,
        'briefing_date': p.briefing_date,
        'designers': designers,
        # Flat string for click-to-sort; designers is the only list column.
        'designers_sort': ', '.join(d['name'] for d in designers if d),
        'client_approved_at': client_approved_at.get(p.id),
        'status_label': status_label,
        'status_class': status_class,
        'status_is_auto': status_is_auto,
        'status_indicators': status_indicators,
        'cs_status': cs.cs_status if cs else None,
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
        'invoice_month': cs.invoice_month_date if cs else None,
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
    """Every non-draft project, eager-loaded, closed ones included. The base
    query for the Calendar, Monthly Summary, Closed, Dashboard and
    _open_projects()."""
    return _eager_load(Project.query).filter(Project.project_status != 'draft')


def _open_projects():
    """_base_projects() minus closed ones; used by the table and Invoicing
    By Project. Left join, so a project with no CS row still lists."""
    return _base_projects().outerjoin(
        ClientServicing, ClientServicing.project_id == Project.id,
    ).filter(ClientServicing.closed_at.is_(None))


def _awaiting_close_out(project):
    """A cancelled project not yet closed. It shows in the close-out strip
    above the table, not in the rows."""
    cs = project.client_servicing
    return project.cancelled_at is not None and not (cs is not None and cs.closed_at is not None)


def _close_out_row(project):
    """One close-out strip entry: enough to identify the project and open
    the close prompt."""
    cs = project.client_servicing
    return {
        'id': project.id,
        'client': project.client_brand.name if project.client_brand else None,
        'name': project.name,
        'cancelled_at': project.cancelled_at,
        # The prompt asks for a value only when the project has none yet.
        'has_value': project.value is not None,
    }


def _page_context():
    """Template context: rows, close-out strip and dropdown options. Contact
    options are keyed by client_id, since a row's Client SPOC must belong to
    its project's client."""
    listed = _open_projects().order_by(Project.name.asc()).all()
    to_close_out = [p for p in listed if _awaiting_close_out(p)]
    projects = [p for p in listed if not _awaiting_close_out(p)]

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
        'status_options': [{'id': label, 'name': label} for label in CS_STATUS_OPTIONS],
        'cs_lead_options': _person_options('cs'),
        'project_owner_options': _person_options('project_owner'),
        'contacts_by_client': _contacts_by_client(client_ids),
        'to_close_out': [_close_out_row(p) for p in to_close_out],
        'can_close': can_close_projects(effective_user()),
    }


@client_servicing_bp.route('/table')
@login_required
@require_cs
def table():
    return render_template('client_servicing/table.html', **_page_context())


@client_servicing_bp.route('/table-rows')
@login_required
@require_cs
def table_rows():
    """Rows fragment for the SSE live refresh; client_servicing.js swaps it
    into #client-servicing-table-body."""
    return render_template('client_servicing/_table_rows.html', **_page_context())
