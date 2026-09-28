"""
Client Servicing — closing a project. Closing is CS-owned and final: it
stamps closed_at on the ClientServicing row. The only Project write is
filling in a missing value.

A cancelled project must answer the invoicing question, so its close
carries invoice_needed and, if already invoiced, the invoice date.
"""
from datetime import date, datetime

from flask import request, jsonify, abort
from flask_login import login_required

from app.modules.core.shared.extensions import db
from app.modules.core.shared.lib.utils import log_activity
from app.modules.core.shared.models import Project

from app.modules.client_servicing.models import ClientServicing
from app.modules.core.shared.lib.capabilities import effective_user
from app.modules.client_servicing.lib.access import can_close_projects, require_cs
from app.modules.client_servicing.routes.blueprint import client_servicing_bp
from app.modules.client_servicing.routes.edit import _FieldError, _parse_money


@client_servicing_bp.route('/<int:project_id>/close', methods=['POST'])
@login_required
@require_cs
def close_project(project_id):
    """Close one project. invoice_needed is None for a normal close and a
    bool for a cancelled one; an invoice_date alongside a True answer means
    it has already been invoiced."""
    actor = effective_user()
    if not can_close_projects(actor):
        abort(403)

    project = Project.query.get_or_404(project_id)
    cs = project.client_servicing
    if cs is not None and cs.closed_at is not None:
        return jsonify({'error': 'That project is already closed.'}), 409

    data = request.get_json(silent=True) or {}
    invoice_needed = data.get('invoice_needed')
    if invoice_needed is not None and not isinstance(invoice_needed, bool):
        return jsonify({'error': 'Answer the invoicing question first.'}), 400
    if project.cancelled_at is not None and invoice_needed is None:
        return jsonify({'error': 'Answer the invoicing question first.'}), 400

    # A project that still needs invoicing must have a value (it feeds the
    # Closed page's Value column and month total). Enforced server-side.
    project_value = None
    raw_value = data.get('project_value')
    if raw_value not in (None, ''):
        try:
            project_value = _parse_money(raw_value)
        except _FieldError as e:
            return jsonify({'error': 'Project value {}.'.format(e)}), 400
    has_value = project_value is not None or project.value is not None
    if invoice_needed and not has_value:
        return jsonify({'error': 'Enter the project value.'}), 400

    invoice_date = None
    raw_date = (data.get('invoice_date') or '').strip()
    if raw_date:
        if not invoice_needed:
            return jsonify({'error': 'Only an invoiced project takes an invoice date.'}), 400
        try:
            invoice_date = date.fromisoformat(raw_date)
        except ValueError:
            return jsonify({'error': 'Enter a valid invoice date.'}), 400

    if cs is None:
        cs = ClientServicing(project_id=project.id)
        db.session.add(cs)
    cs.closed_at = datetime.utcnow()
    cs.closed_by_id = actor.id
    cs.invoice_needed = invoice_needed
    if project_value is not None:
        # Direct write, skipping project mutations: a close-out data fill needs
        # no notification, and the close logs its own activity entry.
        project.value = float(project_value)
    if invoice_date is not None:
        cs.invoice_date = invoice_date
    db.session.commit()

    verb = 'closed out the cancelled project' if project.cancelled_at else 'closed the project'
    log_activity(
        action='client_servicing_close',
        description=f'{actor.name} {verb} in Client Servicing',
        user=actor,
        entity_type='project',
        entity_name=project.name,
        entity_id=project.id,
    )
    return jsonify({'status': 'ok'})
