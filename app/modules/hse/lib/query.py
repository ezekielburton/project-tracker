"""
The register list query, and the counts the rail and the filter chips read.

Every list here is eager-loaded in one round trip: a register row shows
five related records, and lazy loading them is the N+1 the dashboard
module is being rebuilt to undo.
"""

from sqlalchemy.orm import selectinload

from app.modules.hse.lib.computed import expiry_status
from app.modules.hse.models import HseEntry


# Most-recent-first cap. No register should reach this, but an unbounded
# list is how a page gets slow quietly.
ROW_LIMIT = 500

# Statuses that mean "still needs someone" — what the rail badges count.
OPEN_STATUSES = ('Open', 'In Progress', 'Escalated')

# Computed expiry statuses that count as needing attention.
OPEN_EXPIRY_STATUSES = ('Expiring soon', 'Expired')


def _eager(query):
    return query.options(
        selectinload(HseEntry.location),
        selectinload(HseEntry.department),
        selectinload(HseEntry.asset),
        selectinload(HseEntry.reported_by),
        selectinload(HseEntry.assigned_to),
        selectinload(HseEntry.subject),
    )


def entries_for(register_key, status=None, today=None):
    """Rows for one register, newest first. `status` filters on the stored
    column, or on the computed expiry status for a register whose status is
    derived — which cannot be a WHERE clause, so it filters in Python over
    the already-loaded page."""
    from app.modules.hse.lib.registers import register

    reg = register(register_key)
    query = _eager(HseEntry.query.filter(HseEntry.register == register_key))

    if status and reg.status_source == 'stored':
        query = query.filter(HseEntry.status == status)

    rows = query.order_by(HseEntry.entry_date.desc(), HseEntry.id.desc()).limit(ROW_LIMIT).all()

    if status and reg.status_source == 'expiry':
        rows = [r for r in rows if expiry_status(r, today) == status]
    return rows


def status_counts(register_key, today=None):
    """Count per status for the filter chips, over the same rows the table
    shows. Derived statuses are counted in Python, for the same reason."""
    from app.modules.hse.lib.registers import register

    reg = register(register_key)
    rows = (HseEntry.query
            .filter(HseEntry.register == register_key)
            .order_by(HseEntry.entry_date.desc(), HseEntry.id.desc())
            .limit(ROW_LIMIT).all())

    counts = {}
    for row in rows:
        label = expiry_status(row, today) if reg.status_source == 'expiry' else row.status
        if label:
            counts[label] = counts.get(label, 0) + 1
    return counts, len(rows)


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
