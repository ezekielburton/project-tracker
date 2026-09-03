"""
Client Servicing — Invoicing section. Two tabs behind an in-page strip:
By Project (the per-project finance table) and Monthly Summary (rollup).
Finance fields are plain ClientServicing columns and read-only here —
editing lives in edit.py.
"""
from flask import render_template, abort, request, jsonify
from flask_login import login_required

from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import Project

from app.modules.client_servicing.models import ClientServicingSetting
from app.modules.client_servicing.lib.access import can_access_client_servicing, _effective_user
from app.modules.client_servicing.routes.blueprint import client_servicing_bp
from app.modules.client_servicing.routes.table import _eager_load


# Who may change the Days Pending colour thresholds.
_THRESHOLD_ROLES = ('admin', 'management')

# Stored validation value -> (pill label, status-pill colour modifier).
# Unknown or unset renders as a blank cell.
_VALIDATION = {
    'valid': ('Valid', 'clover'),
    'pending': ('Pending', 'canary'),
    'no_lpo': ('No LPO', 'salmon'),
    'overdue': ('Overdue', 'salmon'),
}


def _fmt_date(d):
    return d.strftime('%d %b') if d else None


def _fmt_amount(v):
    return '{:,.0f}'.format(v) if v is not None else None


def _days_cell(days, green_max, red_max):
    """(label, pill colour) for Days Pending. None when there's no date to
    measure from — the cell renders a muted dash, not a badge."""
    if days is None:
        return None, None
    if days <= green_max:
        return '{}d'.format(days), 'clover'
    if days <= red_max:
        return '{}d'.format(days), 'canary'
    return '{}d'.format(days), 'salmon'


def _finance_row(p, green_max, red_max):
    """One By-Project row: the finance columns plus the two computed values
    (days pending, margin), pre-formatted for display."""
    cs = p.client_servicing
    days = cs.days_pending if cs else None
    margin = cs.margin_percent if cs else None
    days_label, days_class = _days_cell(days, green_max, red_max)
    return {
        'id': p.id,
        'project': p.name,
        'client': p.client_brand.name if p.client_brand else None,
        'lpo': cs.lpo if cs else None,
        'lpo_date': _fmt_date(cs.lpo_date if cs else None),
        'project_value': _fmt_amount(cs.project_value if cs else None),
        'invoice_number': cs.invoice_number if cs else None,
        'invoice_date': _fmt_date(cs.invoice_date if cs else None),
        'invoice_amount': _fmt_amount(cs.invoice_amount if cs else None),
        'invoice_month': cs.invoice_month if cs else None,
        'margin': '{:.0f}%'.format(margin) if margin is not None else None,
        'days_label': days_label,
        'days_class': days_class,
        'gr_received': bool(cs.gr_received) if cs else False,
        'validation': _VALIDATION.get(cs.validation_status) if cs else None,
    }


def _rows(settings):
    projects = _eager_load(Project.query).order_by(Project.name.asc()).all()
    return [_finance_row(p, settings.days_green_max, settings.days_red_max) for p in projects]


@client_servicing_bp.route('/invoicing')
@login_required
def invoicing():
    actor = _effective_user()
    if not can_access_client_servicing(actor):
        abort(403)
    settings = ClientServicingSetting.current()
    return render_template(
        'client_servicing/invoicing.html',
        rows=_rows(settings),
        settings=settings,
        can_edit_thresholds=getattr(actor, 'role', None) in _THRESHOLD_ROLES,
    )


@client_servicing_bp.route('/invoicing/summary')
@login_required
def invoicing_summary():
    if not can_access_client_servicing(_effective_user()):
        abort(403)
    return render_template('client_servicing/invoicing_summary.html')


@client_servicing_bp.route('/invoicing/day-thresholds', methods=['POST'])
@login_required
def save_day_thresholds():
    if getattr(_effective_user(), 'role', None) not in _THRESHOLD_ROLES:
        abort(403)
    data = request.get_json(silent=True) or {}
    try:
        green = int(data.get('days_green_max'))
        red = int(data.get('days_red_max'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Both values must be whole numbers.'}), 400
    if green < 1 or red < 1:
        return jsonify({'error': 'Values must be at least 1 day.'}), 400
    if green >= red:
        return jsonify({'error': 'Green must be fewer days than amber.'}), 400

    row = ClientServicingSetting.query.first()
    if row is None:
        row = ClientServicingSetting()
        db.session.add(row)
    row.days_green_max = green
    row.days_red_max = red
    db.session.commit()
    return jsonify({'status': 'ok'})
