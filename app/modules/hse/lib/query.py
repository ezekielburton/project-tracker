"""
The register list query, and the counts the rail and the filter chips read.

Every list here is eager-loaded in one round trip: a register row shows
five related records, and lazy loading them is the N+1 the dashboard
module is being rebuilt to undo.

Filtering and paging both happen here rather than in the route, so the
chip counts and the rows they filter can never be built from two different
sets.
"""

from datetime import date, timedelta

from sqlalchemy import Text, cast, extract, func, or_
from sqlalchemy.orm import aliased, selectinload

from app.modules.hse.lib.computed import expiry_status
# Re-exported: these are vocabulary, and lib/vocab.py stays importable without
# the models so the metric code can read the same set.
from app.modules.hse.lib.vocab import (  # noqa: F401
    OPEN_EXPIRY_STATUSES, OPEN_STATUSES,
)
from app.modules.hse.models import HseAsset, HseEntry, HsePerson, HseReference


# Rows per page. Small enough that the table never needs its own scrollbar
# on a laptop, which is what the wireframe shows.
PAGE_SIZE = 25

# How far back the Overview looks. An incident ages out of usefulness; a
# certificate does not.
DASHBOARD_LOOKBACK_DAYS = 400


def _eager(query):
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
    """The no-filter state, so callers never have to remember the keys."""
    return {'status': None, 'severity': None, 'year': None, 'search': None}


def _searched(query, term):
    """Free text across the ref, everything in the JSONB blob, and the names
    behind the foreign keys.

    The joins only go on when someone is actually searching — they are seven
    outer joins, and every unfiltered page load would otherwise pay for
    them.
    """
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
        # The JSONB blob holds every unpromoted field. Promoted choices (the
        # compliance item) live on their reference row, joined below.
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
    """Everything except the status filter — the set the chips count over,
    so a chip shows how many rows it would land on, not how many exist."""
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
    """The years this register actually holds rows in, newest first. A year
    with nothing in it is not offered — an empty filter is a dead end."""
    rows = (HseEntry.query
            .with_entities(extract('year', HseEntry.entry_date))
            .filter(HseEntry.register == register_key)
            .distinct().all())
    return sorted({int(r[0]) for r in rows if r[0] is not None}, reverse=True)


def page_of(register_key, filters, page=1, today=None):
    """One page of a register, with the chip counts that go above it.

    A stored status is a column, so both the counts and the page are SQL. A
    computed expiry status is neither — it is a function of due_at and the
    date — so that branch loads the matching rows and does the work in
    Python. Compliance is the only expiry register and it holds certificates,
    not events, so the set stays small by nature.
    """
    from app.modules.hse.lib.registers import register

    reg = register(register_key)
    matching = _matching(register_key, filters)
    status = filters.get('status')

    if reg.status_source == 'expiry':
        rows = _ordered(_eager(matching)).all()
        counts = {}
        for row in rows:
            label = expiry_status(row, today)
            if label:
                counts[label] = counts.get(label, 0) + 1
        # Count the chips first, then total from them — same definition as
        # the stored branch, so "All" can never disagree with the chips it
        # sits above (a row with no expiry status has no chip and no place in
        # the total).
        total_all = sum(counts.values())
        if status:
            rows = [r for r in rows if expiry_status(r, today) == status]
        total = len(rows)
        page_rows = rows[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]
    else:
        counts = dict(matching
                      .with_entities(HseEntry.status, func.count(HseEntry.id))
                      .group_by(HseEntry.status).all())
        counts.pop(None, None)
        total_all = sum(counts.values())
        query = matching.filter(HseEntry.status == status) if status else matching
        total = query.with_entities(func.count(HseEntry.id)).scalar() or 0
        page_rows = (_ordered(_eager(query))
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


def open_counts_by_group(today=None):
    """Open-item count per rail group, for the rail badges. One pass over
    the open rows rather than a query per group."""
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
        # A log has no open items — it must not inflate a rail badge.
        if reg.status_source == 'none':
            continue
        if register_key in expiry_registers:
            label = expiry_status(_DueOnly(due_at, closed_at), today)
            hit = label in OPEN_EXPIRY_STATUSES
        else:
            hit = status in OPEN_STATUSES
        if hit:
            counts[reg.group] = counts.get(reg.group, 0) + 1
    return counts


class _DueOnly:
    """The two fields expiry_status reads, so the group-count query can stay
    a lightweight column select instead of loading whole entries."""

    def __init__(self, due_at, closed_at):
        self.due_at = due_at
        self.closed_at = closed_at



def dashboard_entries(today=None, lookback=DASHBOARD_LOOKBACK_DAYS):
    """The entry set the Overview and My performance both read.

    One function on purpose. The metric definitions are already shared, but
    two routes with two different windows still give two different answers
    to "compliance health" — which is the drift sharing them was meant to
    stop.

    **Anything carrying a due date is loaded whatever its issue date.** An
    event more than a year old is history; a five-year licence issued in
    2024 is the most current thing the site owns, and filtering it out by
    issue date makes it silently vanish from the number that counts it.
    """
    today = today or date.today()
    cutoff = today - timedelta(days=lookback)
    return (_eager(HseEntry.query)
            .options(selectinload(HseEntry.waiting_on))
            .filter(or_(HseEntry.entry_date >= cutoff,
                        HseEntry.due_at.isnot(None)))
            .all())
