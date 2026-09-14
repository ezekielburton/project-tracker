"""
HSE — the one register surface, for all twenty-one.

Columns, filter chips and the empty state all render from HSE_REGISTERS, so
adding a register stays one entry in that declaration rather than a new
route, template and form.
"""
from datetime import date

from flask import abort, redirect, render_template, request, url_for
from flask_login import login_required

from app.modules.core.shared.lib.capabilities import require
from app.modules.hse.lib.query import (
    ROW_LIMIT, entries_for, open_counts_by_group, status_counts,
)
from app.modules.hse.lib.rail import rail_items
from app.modules.hse.lib.registers import register, registers_in_group
from app.modules.hse.lib.table import columns, status_chips, table_rows
from app.modules.hse.routes.blueprint import hse_bp


@hse_bp.route('/')
@login_required
@require('view_hse')
def index():
    """The module's front door. The Overview answers "what needs me today",
    which is why he opened it — a register is where he goes next."""
    return redirect(url_for('hse.overview'))


@hse_bp.route('/<group_key>')
@login_required
@require('view_hse')
def group_page(group_key):
    registers = registers_in_group(group_key)
    if not registers:
        abort(404)
    return redirect(url_for('hse.register_page',
                            group_key=group_key, register_key=registers[0].key))


@hse_bp.route('/<group_key>/<register_key>')
@login_required
@require('view_hse')
def register_page(group_key, register_key):
    reg = register(register_key)
    if reg is None or reg.group != group_key:
        abort(404)

    today = date.today()
    status = request.args.get('status') or None
    counts, total = status_counts(register_key, today)
    if status and status not in counts:
        status = None

    entries = entries_for(register_key, status, today)
    return render_template(
        'hse/registers.html',
        reg=reg,
        tabs=registers_in_group(group_key),
        rail=rail_items(open_counts_by_group(today), active_group=group_key),
        active_group=group_key,
        columns=columns(reg),
        rows=table_rows(entries, reg, today),
        chips=status_chips(reg, counts, total, today),
        active_status=status,
        truncated=total >= ROW_LIMIT,
    )
