"""
The register list query, and the counts the rail and filter chips read.

Rows eager-load their related records to avoid N+1 queries. Filtering and
paging both live here so chip counts and rows come from the same set.
"""

from collections import namedtuple
from datetime import date, timedelta

from sqlalchemy import Text, and_, cast, extract, func, or_
from sqlalchemy.orm import aliased, selectinload

from app.modules.hse.lib.computed import expiry_status
# Re-exported; defined in lib/vocab.py so metric code can import them
# without the models.
from app.modules.hse.lib.vocab import (  # noqa: F401
    OPEN_EXPIRY_STATUSES, OPEN_STATUSES,
)
from app.modules.hse.models import HseAsset, HseEntry, HsePerson, HseReference


# Rows per page.
PAGE_SIZE = 25

# How far back the Overview looks (entries with a due_at are always loaded).
DASHBOARD_LOOKBACK_DAYS = 400


def eager(query):
    """The query with every related record the tables and titles read."""
    return query.options(
        selectinload(HseEntry.location),
        selectinload(HseEntry.department),
        selectinload(HseEntry.asset),
        selectinload(HseEntry.reported_by),
        selectinload(HseEntry.assigned_to),
        selectinload(HseEntry.subject),
        selectinload(HseEntry.compliance_item),
    )


def empty_filters():
    """The no-filter state, so callers never have to remember the keys.
    `flag` is a flag chip's value; `ids` the entries it keeps."""
    return {'status': None, 'severity': None, 'year': None, 'search': None,
            'flag': None, 'ids': None}


def _only(query, ids):
    """Rows among `ids`, when a flag chip is on."""
    if ids is None:
        return query
    return query.filter(HseEntry.id.in_(list(ids) or [0]))


def count_matching(register_key, filters, ids=None):
    """Rows the non-status filters match, optionally only among `ids`: the
    All and flag chip counts on a register with flag chips."""
    query = _only(_matching(register_key, filters), ids)
    return query.with_entities(func.count(HseEntry.id)).scalar() or 0


def _searched(query, term):
    """Free-text filter across ref, status, the JSONB blob, and the names
    behind the foreign keys. Adds seven outer joins, so only call it when
    there is a search term."""
    like = f'%{term}%'
    location, department = aliased(HseReference), aliased(HseReference)
    compliance = aliased(HseReference)
    asset = aliased(HseAsset)
    reporter, owner, subject = aliased(HsePerson), aliased(HsePerson), aliased(HsePerson)

    query = (query
             .outerjoin(location, HseEntry.location_id == location.id)
             .outerjoin(department, HseEntry.department_id == department.id)
             .outerjoin(compliance, HseEntry.compliance_item_id == compliance.id)
             .outerjoin(asset, HseEntry.asset_id == asset.id)
             .outerjoin(reporter, HseEntry.reported_by_id == reporter.id)
             .outerjoin(owner, HseEntry.assigned_to_id == owner.id)
             .outerjoin(subject, HseEntry.subject_id == subject.id))

    return query.filter(or_(
        HseEntry.ref.ilike(like),
        HseEntry.status.ilike(like),
        # Unpromoted fields. Promoted ones are matched via the joins above.
        cast(HseEntry.data, Text).ilike(like),
        location.label.ilike(like),
        department.label.ilike(like),
        compliance.label.ilike(like),
        asset.label.ilike(like),
        asset.ref.ilike(like),
        reporter.name.ilike(like),
        owner.name.ilike(like),
        subject.name.ilike(like),
    ))


def _matching(register_key, filters):
    """All filters except status: the set the chips count over, so each
    chip shows how many rows it would land on."""
    query = HseEntry.query.filter(HseEntry.register == register_key)
    if filters.get('severity'):
        query = query.filter(HseEntry.severity == filters['severity'])
    if filters.get('year'):
        query = query.filter(extract('year', HseEntry.entry_date) == filters['year'])
    if filters.get('search'):
        query = _searched(query, filters['search'].strip())
    return query


def _ordered(query):
    return query.order_by(HseEntry.entry_date.desc(), HseEntry.id.desc())


def years_for(register_key):
    """Years this register has rows in, newest first."""
    rows = (HseEntry.query
            .with_entities(extract('year', HseEntry.entry_date))
            .filter(HseEntry.register == register_key)
            .distinct().all())
    return sorted({int(r[0]) for r in rows if r[0] is not None}, reverse=True)


def page_of(register_key, filters, page=1, today=None):
    """One page of a register, with its chip counts. Stored statuses count
    and page in SQL. Expiry statuses are computed, so that branch loads all
    matching rows and works in Python; expiry registers hold documents and
    issued PPE, so the sets stay small. A grouped register also returns
    'groups' and pages whole groups."""
    from app.modules.hse.lib.registers import register

    reg = register(register_key)
    matching = _matching(register_key, filters)
    status = filters.get('status')

    if reg.status_source == 'expiry':
        rows = _ordered(eager(matching)).all()
        counts = {}
        for row in rows:
            label = expiry_status(row, today)
            if label:
                counts[label] = counts.get(label, 0) + 1
        # "All" is the sum of the chips, as in the stored branch; rows with
        # no expiry status are left out of both.
        total_all = sum(counts.values())
        if status:
            rows = [r for r in rows if expiry_status(r, today) == status]
        total = len(rows)
        if reg.group_by:
            return _grouped_page(reg, rows, page, counts, total_all)
        page_rows = rows[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]
    else:
        counts = dict(matching
                      .with_entities(HseEntry.status, func.count(HseEntry.id))
                      .group_by(HseEntry.status).all())
        counts.pop(None, None)
        total_all = sum(counts.values())
        query = matching.filter(HseEntry.status == status) if status else matching
        query = _only(query, filters.get('ids'))
        total = query.with_entities(func.count(HseEntry.id)).scalar() or 0
        page_rows = (_ordered(eager(query))
                     .limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE).all())

    pages = max(1, -(-total // PAGE_SIZE))  # ceiling division
    return {
        'rows': page_rows,
        'counts': counts,
        'total': total,
        'total_all': total_all,
        'page': page,
        'pages': pages,
        'first': 0 if not total else (page - 1) * PAGE_SIZE + 1,
        'last': min(page * PAGE_SIZE, total),
    }


def _group_label(entry, field):
    """The name behind a group_by field: the related record's name or
    label, or the JSONB value."""
    if field.column is None:
        return (entry.data or {}).get(field.name)
    related = getattr(entry, field.column[:-len('_id')], None)
    return getattr(related, 'name', None) or getattr(related, 'label', None)


def groups_of(reg, rows):
    """Rows grouped by the register's group_by field: groups A-Z by name,
    rows in their existing order, anything ungrouped last."""
    field = next(f for f in reg.fields if f.name == reg.group_by)
    groups = {}
    for row in rows:
        key = (getattr(row, field.column) if field.column
               else (row.data or {}).get(field.name))
        groups.setdefault(key, []).append(row)
    return sorted(groups.values(), key=lambda g: (
        _group_label(g[0], field) is None,
        (_group_label(g[0], field) or '').casefold()))


def _grouped_page(reg, rows, page, counts, total_all):
    """page_of for a grouped register. A page takes whole groups until it
    holds PAGE_SIZE rows or more, so one group never splits across pages."""
    pages, current = [], []
    for group in groups_of(reg, rows):
        current.append(group)
        if sum(len(g) for g in current) >= PAGE_SIZE:
            pages.append(current)
            current = []
    if current:
        pages.append(current)

    groups = pages[page - 1] if page <= len(pages) else []
    before = sum(len(g) for p in pages[:page - 1] for g in p)
    shown = sum(len(g) for g in groups)
    return {
        'rows': [r for g in groups for r in g],
        'groups': groups,
        'counts': counts,
        'total': len(rows),
        'total_all': total_all,
        'page': page,
        'pages': max(1, len(pages)),
        'first': before + 1 if shown else 0,
        'last': before + shown,
    }


def latest_ids(register_key):
    """Ids of the latest entry per asset in a register: the ones with a
    next due date."""
    rows = (HseEntry.query
            .with_entities(HseEntry.id)
            .filter(HseEntry.register == register_key, HseEntry.asset_id.isnot(None))
            .distinct(HseEntry.asset_id)
            .order_by(HseEntry.asset_id, HseEntry.entry_date.desc(), HseEntry.id.desc())
            .all())
    return {r[0] for r in rows}


def open_counts_by_register(today=None):
    """Open-item count per register key, for the rail badges. One pass over
    rows with no closed_at."""
    from app.modules.hse.lib.registers import BY_KEY

    expiry_registers = [k for k, r in BY_KEY.items() if r.status_source == 'expiry']

    rows = (HseEntry.query
            .with_entities(HseEntry.register, HseEntry.status,
                           HseEntry.due_at, HseEntry.closed_at)
            .filter(HseEntry.closed_at.is_(None))
            .all())

    counts = {}
    for register_key, status, due_at, closed_at in rows:
        reg = BY_KEY.get(register_key)
        if reg is None:
            continue
        # Logs have no open items.
        if reg.status_source == 'none':
            continue
        if register_key in expiry_registers:
            label = expiry_status(_DueOnly(due_at, closed_at), today)
            hit = label in OPEN_EXPIRY_STATUSES
        else:
            hit = status in OPEN_STATUSES
        if hit:
            counts[register_key] = counts.get(register_key, 0) + 1
    return counts


class _DueOnly:
    """Stand-in carrying the fields expiry_status reads, so the count query
    can select columns only."""

    def __init__(self, due_at, closed_at):
        self.due_at = due_at
        self.closed_at = closed_at



SpendRow = namedtuple('SpendRow', 'register entry_date data')


def spend_entries(register_keys=None, filters=None, today=None):
    """All-time rows from registers with a money field, money values only:
    the one loader for the Overview panel and the register strip. `filters`
    (one register) applies the table's status, severity and search, not year."""
    from app.modules.hse.lib.registers import BY_KEY, money_fields, money_registers

    regs = ([BY_KEY[k] for k in register_keys if k in BY_KEY]
            if register_keys is not None else list(money_registers()))
    regs = [r for r in regs if money_fields(r)]
    if not regs:
        return []
    names = sorted({fl.name for r in regs for fl in money_fields(r)})

    if filters:
        if len(regs) != 1:
            raise ValueError('Filters apply to one register')
        reg = regs[0]
        query = _matching(reg.key, dict(filters, year=None))
        status = filters.get('status')
    else:
        reg, status = None, None
        query = HseEntry.query.filter(HseEntry.register.in_([r.key for r in regs]))

    # Expiry statuses are computed, so that filter runs in Python below.
    by_expiry = bool(status) and reg.status_source == 'expiry'
    if status and not by_expiry:
        query = query.filter(HseEntry.status == status)
    if filters:
        query = _only(query, filters.get('ids'))

    columns = [HseEntry.register, HseEntry.entry_date]
    columns += [HseEntry.data[name].astext for name in names]
    if by_expiry:
        columns += [HseEntry.due_at, HseEntry.closed_at]

    out = []
    for row in query.with_entities(*columns).all():
        if by_expiry and expiry_status(_DueOnly(row[-2], row[-1]), today) != status:
            continue
        values = row[2:2 + len(names)]
        data = {n: v for n, v in zip(names, values) if v is not None}
        out.append(SpendRow(row[0], row[1], data))
    return out


# Read by Statistics whatever their date: stock lines (their movements carry
# the dates), every PM job (on time is judged against the one before), every
# LTI (days since the last) and unclosed inspections (still open).
_STATISTICS_ALWAYS = ('materials_in_stock', 'machine_preventive', 'lost_time_injury')
_INSPECTIONS = ('general_inspection', 'vehicle_inspection', 'forklift_inspection')


def statistics_entries(since):
    """Entries dated from `since`, plus the undated needs above."""
    return (eager(HseEntry.query)
            .filter(or_(HseEntry.entry_date >= since,
                        HseEntry.register.in_(_STATISTICS_ALWAYS),
                        and_(HseEntry.register.in_(_INSPECTIONS),
                             HseEntry.closed_at.is_(None))))
            .all())


def first_entry_year():
    """The year of the oldest entry, or None when there are none."""
    first = HseEntry.query.with_entities(func.min(HseEntry.entry_date)).scalar()
    return first.year if first else None


def dashboard_entries(today=None, lookback=DASHBOARD_LOOKBACK_DAYS):
    """The entry set both the Overview and My performance read, so their
    metrics use the same window. Entries dated within the lookback, plus any
    entry with a due_at regardless of age (a long-lived licence must still
    count)."""
    today = today or date.today()
    cutoff = today - timedelta(days=lookback)
    return (eager(HseEntry.query)
            .options(selectinload(HseEntry.waiting_on))
            .filter(or_(HseEntry.entry_date >= cutoff,
                        HseEntry.due_at.isnot(None)))
            .all())
