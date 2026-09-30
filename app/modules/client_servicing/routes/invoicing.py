"""
Client Servicing — Invoicing. Two side-rail sub-pages: By Project (the
per-project finance table, plus CSV export) and Monthly Summary (rollup).
Finance-field edits go through edit.py; this file only writes the
Days Pending thresholds.
"""
import csv
import io
from datetime import date

from flask import render_template, abort, request, jsonify, Response
from flask_login import login_required

from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import Project

from app.modules.client_servicing.models import ClientServicing, ClientServicingSetting
from app.modules.core.shared.lib.capabilities import can, effective_user
from app.modules.client_servicing.lib.access import require_cs
from app.modules.client_servicing.lib.months import format_month, month_input_value, parse_month
from app.modules.client_servicing.routes.blueprint import client_servicing_bp
from app.modules.client_servicing.routes.table import _active_projects
from app.modules.client_servicing.lib import summary as summary_lib

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
    """(label, pill colour) for Days Pending; (None, None) when there is no
    date to measure from."""
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
        'project_value': _fmt_amount(p.value),
        'invoice_number': cs.invoice_number if cs else None,
        'invoice_date': _fmt_date(cs.invoice_date if cs else None),
        'invoice_amount': _fmt_amount(cs.invoice_amount if cs else None),
        'invoice_month': format_month(cs.invoice_month_date if cs else None),
        'margin': '{:.0f}%'.format(margin) if margin is not None else None,
        'days_label': days_label,
        'days_class': days_class,
        'gr_received': bool(cs.gr_received) if cs else False,
        'validation': _VALIDATION.get(cs.validation_status) if cs else None,
        # Raw values for the inline editors (ISO dates, plain numbers).
        'lpo_date_iso': cs.lpo_date.isoformat() if (cs and cs.lpo_date) else '',
        'invoice_date_iso': cs.invoice_date.isoformat() if (cs and cs.invoice_date) else '',
        'invoice_month_raw': month_input_value(cs.invoice_month_date if cs else None),
        'project_value_raw': str(p.value) if p.value is not None else '',
        'invoice_amount_raw': str(cs.invoice_amount) if (cs and cs.invoice_amount is not None) else '',
        'validation_value': (cs.validation_status if cs else '') or '',
    }


def _filter_args():
    """(invoice_month, validation) from the query string. invoice_month
    comes in as YYYY-MM and returns as the 1st of that month. Blank or
    unreadable values mean All."""
    invoice_month = parse_month((request.args.get('invoice_month') or '').strip())
    validation = (request.args.get('validation') or '').strip()
    if validation and validation != 'none' and validation not in _VALIDATION:
        validation = ''
    return invoice_month, validation


def _invoice_month_options():
    """(value, label) for every invoice month in use, newest first."""
    rows = (
        db.session.query(ClientServicing.invoice_month_date)
        .filter(ClientServicing.invoice_month_date.isnot(None))
        .distinct()
        .order_by(ClientServicing.invoice_month_date.desc())
        .all()
    )
    return [(month_input_value(row[0]), format_month(row[0])) for row in rows]


def _filtered_projects(invoice_month, validation):
    """The active set narrowed by the toolbar filters. Shared by the page and
    the CSV export so both filter the same way."""
    query = _active_projects()
    if invoice_month:
        query = query.filter(ClientServicing.invoice_month_date == invoice_month)
    if validation == 'none':
        query = query.filter(ClientServicing.validation_status.is_(None))
    elif validation:
        query = query.filter(ClientServicing.validation_status == validation)
    return query.order_by(Project.name.asc()).all()


def _rows(settings, projects):
    return [_finance_row(p, settings.days_green_max, settings.days_red_max) for p in projects]


@client_servicing_bp.route('/invoicing')
@login_required
@require_cs
def invoicing():
    actor = effective_user()
    settings = ClientServicingSetting.current()
    invoice_month, validation = _filter_args()
    return render_template(
        'client_servicing/invoicing.html',
        rows=_rows(settings, _filtered_projects(invoice_month, validation)),
        settings=settings,
        invoice_month=month_input_value(invoice_month),
        validation=validation,
        invoice_month_options=_invoice_month_options(),
        validation_options=[(code, label) for code, (label, _) in _VALIDATION.items()],
        can_edit_thresholds=can('edit_invoicing_thresholds', actor),
        can_edit_finance=can('edit_finance', actor),
    )


def _money_cell(value):
    """Money with two decimals, so Float-backed values don't export as 100.0."""
    if value is None:
        return ''
    return '{:.2f}'.format(value)


# CSV header -> reader(project, cs). Raw values only: ISO dates, plain numbers.
_EXPORT_COLUMNS = [
    ('Project', lambda p, cs: p.name),
    ('Client', lambda p, cs: p.client_brand.name if p.client_brand else ''),
    ('LPO / PO Number', lambda p, cs: cs.lpo if cs else ''),
    ('LPO Date', lambda p, cs: cs.lpo_date.isoformat() if (cs and cs.lpo_date) else ''),
    ('Project Value AED', lambda p, cs: _money_cell(p.value)),
    ('Invoice Number', lambda p, cs: cs.invoice_number if cs else ''),
    ('Invoice Date', lambda p, cs: cs.invoice_date.isoformat() if (cs and cs.invoice_date) else ''),
    ('Invoice Amount AED', lambda p, cs: _money_cell(cs.invoice_amount if cs else None)),
    ('Invoice Month', lambda p, cs: month_input_value(cs.invoice_month_date) if cs else ''),
    ('Margin %', lambda p, cs: round(cs.margin_percent, 2) if (cs and cs.margin_percent is not None) else ''),
    ('Days Pending', lambda p, cs: cs.days_pending if (cs and cs.days_pending is not None) else ''),
    ('GR Received', lambda p, cs: 'yes' if (cs and cs.gr_received) else 'no'),
    ('Invoice Uploaded', lambda p, cs: 'yes' if (cs and cs.invoice_uploaded) else 'no'),
    ('Validation', lambda p, cs: (cs.validation_status if cs else '') or ''),
]


@client_servicing_bp.route('/invoicing/export.csv')
@login_required
@require_cs
def invoicing_export():
    """The filtered By Project rows as CSV. The toolbar search box is
    client-side only, so it does not apply here."""
    invoice_month, validation = _filter_args()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([header for header, _ in _EXPORT_COLUMNS])
    for project in _filtered_projects(invoice_month, validation):
        cs = project.client_servicing
        writer.writerow([read(project, cs) for _, read in _EXPORT_COLUMNS])

    return Response(
        buffer.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=client-servicing-invoicing.csv'},
    )


@client_servicing_bp.route('/invoicing/summary')
@login_required
@require_cs
def invoicing_summary():
    today = date.today()

    def _arg(name, default):
        try:
            return int(request.args.get(name, default))
        except (TypeError, ValueError):
            return default

    year = _arg('year', today.year)
    month = _arg('month', today.month)
    if not 1 <= month <= 12:
        month = today.month

    rows, total = summary_lib.year_summary(year)
    kpi = rows[month - 1]
    due = summary_lib.due_this_month(year, month)
    for d in due:
        d['validation'] = _VALIDATION.get(d['validation'])

    years = list(range(today.year - 3, today.year + 2))
    months = [(m, date(2000, m, 1).strftime('%B')) for m in range(1, 13)]

    return render_template(
        'client_servicing/invoicing_summary.html',
        year=year, month=month, rows=rows, total=total, kpi=kpi, due=due,
        years=years, months=months, current_year=today.year, current_month=today.month,
    )


@client_servicing_bp.route('/invoicing/day-thresholds', methods=['POST'])
@login_required
def save_day_thresholds():
    if not can('edit_invoicing_thresholds', effective_user()):
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
