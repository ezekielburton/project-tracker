"""
HSE register pages: one route and template serves every register.

Columns, filter chips and the empty state render from HSE_REGISTERS, so a
new register is one entry there. All filters live in the URL, so a view
survives refresh and can be shared.
"""
from datetime import date

from flask import abort, redirect, render_template, request, url_for
from flask_login import login_required

from app.modules.core.shared.lib.capabilities import require
from app.modules.hse.lib.query import (
    empty_filters, open_counts_by_register, page_of, spend_entries, years_for,
)
from app.modules.hse.lib.rail import rail_items
from app.modules.hse.lib.registers import money_fields, register, registers_in_group
from app.modules.hse.lib.spend import spend_strip
from app.modules.hse.lib.table import columns, status_chips, table_rows
from app.modules.hse.models import SEVERITIES
from app.modules.hse.routes.blueprint import hse_bp


@hse_bp.route('/')
@login_required
@require('view_hse')
def index():
    """Module root; redirects to the Overview."""
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
    """Filters from the query string, validated against this register.
    An invalid value means no filter, so a bad URL never shows an empty table."""
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

    # A status this register cannot show is dropped and the page rebuilt.
    status = request.args.get('status') or None
    filters['status'] = status

    page = page_of(register_key, filters, _page_number(), today)
    if filters['status'] and not page['rows'] and filters['status'] not in page['counts']:
        filters['status'] = None
        page = page_of(register_key, filters, 1, today)

    # Every link on the page is this view with one thing changed; a new
    # filter only needs an entry in `carried`.
    carried = {k: v for k, v in (
        ('status', filters['status']), ('severity', filters['severity']),
        ('year', filters['year']), ('q', filters['search'])) if v}

    def link(**changed):
        args = dict(carried, group_key=group_key, register_key=register_key)
        args.update(changed)
        return url_for('hse.register_page',
                       **{k: v for k, v in args.items() if v is not None})

    # Cost registers only. Same filters as the table except year, which picks
    # the month-by-month year instead.
    spend = None
    if money_fields(reg):
        spend = spend_strip(spend_entries((reg.key,), filters, today),
                            filters['year'] or today.year, today)

    chips = status_chips(reg, page['counts'], page['total_all'], today)
    for chip in chips:
        # Reset to page 1, or a narrower filter can land on an empty page.
        chip['url'] = link(status=chip['value'], page=None)

    return render_template(
        'hse/registers.html',
        reg=reg,
        rail=rail_items(open_counts_by_register(today), active_group=group_key),
        active_group=group_key,
        active_sub=reg.key,
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
        spend=spend,
    )


def _has_severity(reg):
    """Only offer the severity filter where the register records one."""
    return any(f.type == 'severity' for f in reg.fields)
