"""
HSE — the one register surface, for all twenty-one.

Columns, filter chips and the empty state all render from HSE_REGISTERS, so
adding a register stays one entry in that declaration rather than a new
route, template and form.

Every filter is a URL parameter, so a filtered view survives a refresh and
can be pasted to someone else. Nothing is held in JavaScript.
"""
from datetime import date

from flask import abort, redirect, render_template, request, url_for
from flask_login import login_required

from app.modules.core.shared.lib.capabilities import require
from app.modules.hse.lib.query import (
    empty_filters, open_counts_by_group, page_of, years_for,
)
from app.modules.hse.lib.rail import rail_items
from app.modules.hse.lib.registers import register, registers_in_group
from app.modules.hse.lib.table import columns, status_chips, table_rows
from app.modules.hse.models import SEVERITIES
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


def _read_filters(reg, years):
    """Filters off the query string, each one validated against what this
    register can actually show. A junk parameter falls back to no filter
    rather than an empty table nobody can explain."""
    filters = empty_filters()

    severity = request.args.get('severity')
    filters['severity'] = severity if severity in SEVERITIES else None

    year = request.args.get('year')
    if year and year.isdigit() and int(year) in years:
        filters['year'] = int(year)

    search = (request.args.get('q') or '').strip()
    filters['search'] = search or None
    return filters


def _page_number():
    raw = request.args.get('page')
    return int(raw) if raw and raw.isdigit() and int(raw) > 0 else 1


@hse_bp.route('/<group_key>/<register_key>')
@login_required
@require('view_hse')
def register_page(group_key, register_key):
    reg = register(register_key)
    if reg is None or reg.group != group_key:
        abort(404)

    today = date.today()
    years = years_for(register_key)
    filters = _read_filters(reg, years)

    # Read after the others, because a status that this register cannot show
    # has to fall back before the page is built rather than after.
    status = request.args.get('status') or None
    filters['status'] = status

    page = page_of(register_key, filters, _page_number(), today)
    if filters['status'] and not page['rows'] and filters['status'] not in page['counts']:
        filters['status'] = None
        page = page_of(register_key, filters, 1, today)

    # Every link on the page is this view with one thing changed, so the
    # URLs are built here rather than reassembled in six places in the
    # template — a new filter is then one entry in `carried`.
    carried = {k: v for k, v in (
        ('status', filters['status']), ('severity', filters['severity']),
        ('year', filters['year']), ('q', filters['search'])) if v}

    def link(**changed):
        args = dict(carried, group_key=group_key, register_key=register_key)
        args.update(changed)
        return url_for('hse.register_page',
                       **{k: v for k, v in args.items() if v is not None})

    chips = status_chips(reg, page['counts'], page['total_all'], today)
    for chip in chips:
        # A chip clears the page number: filtering to eleven rows while
        # sitting on page 3 shows an empty table and looks broken.
        chip['url'] = link(status=chip['value'], page=None)

    return render_template(
        'hse/registers.html',
        reg=reg,
        tabs=registers_in_group(group_key),
        rail=rail_items(open_counts_by_group(today), active_group=group_key),
        active_group=group_key,
        columns=columns(reg),
        rows=table_rows(page['rows'], reg, today),
        chips=chips,
        prev_url=link(page=page['page'] - 1) if page['page'] > 1 else None,
        next_url=link(page=page['page'] + 1) if page['page'] < page['pages'] else None,
        filters=filters,
        carried=carried,
        severities=SEVERITIES if _has_severity(reg) else (),
        years=years,
        page=page,
    )


def _has_severity(reg):
    """Only offer the severity filter where the register records one."""
    return any(f.type == 'severity' for f in reg.fields)
