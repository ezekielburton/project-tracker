# Performance rollup builder + the month/quarter freeze. get_period_rollup() is
# the one entry point routes/performance.py calls: it returns the same shape
# whether the numbers came from a live query or a frozen DiPeriodSnapshot row.
#
# Weekly periods are always computed live — DiPeriodSnapshot only ever holds
# 'month'/'quarter'. A month or quarter freezes automatically on first view once
# it has fully ended; until then it's recomputed live. Once frozen, every field
# (including a project's name/colour) is locked to freeze-time — that's the point.
#
# Every number here is JSON-serializable, since the whole rollup is written into
# DiPeriodSnapshot.snapshot_data as-is when a period freezes.

from sqlalchemy import func

from app.modules.core.shared.extensions import db
from app.modules.digital_innovation.lib import periods, costs
from app.modules.digital_innovation.models import (
    DiCostEntry, DiPeriodSnapshot, DI_STAGE_COLOURS, DI_COST_TYPES, stage_label,
)

# Lower-case labels for the "Total cost" card caption — its own map, separate
# from costs.py's Title-Case DI_COST_TYPE_LABELS (a different display context).
_COST_TYPE_CAPTION_LABELS = {
    'dev_time': 'dev',
    'claude': 'Claude',
    'hardware': 'hardware',
    'licensing': 'licensing',
}


def get_period_rollup(period_type, period_key):
    """The one entry point Performance uses. Returns the rollup dict for
    period_type/period_key — freshly computed for a week, or for a
    still-open/current month or quarter, or read straight from a frozen
    DiPeriodSnapshot for one that has already ended."""
    if period_type in ('month', 'quarter') and periods.period_has_ended(period_type, period_key):
        existing = DiPeriodSnapshot.query.filter_by(period_type=period_type, period_key=period_key).first()
        if existing:
            return existing.snapshot_data
        rollup = _compute_rollup(period_type, period_key)
        db.session.add(DiPeriodSnapshot(period_type=period_type, period_key=period_key, snapshot_data=rollup))
        db.session.commit()
        return rollup
    return _compute_rollup(period_type, period_key)


def _compute_rollup(period_type, period_key):
    period_start, period_end = periods.period_bounds(period_type, period_key)
    overlapping = periods.projects_overlapping(period_start, period_end)
    project_ids = [p.id for p in overlapping]

    dev_hours_by_project, dev_hours_by_feature = _period_dev_hours(project_ids, period_start, period_end)
    period_cost = _period_total_cost(project_ids, period_start, period_end)
    cost_types_present = _period_cost_types(project_ids, period_start, period_end)

    project_rows = []
    closed_profit = 0.0
    projected_profit = 0.0
    closed_project_count = 0

    for project in overlapping:
        summary = costs.cost_summary(project)
        profit = summary['projected_profit']
        is_closed = project.lifecycle in ('closed', 'archived')

        if profit is not None:
            if is_closed:
                closed_profit += profit
                closed_project_count += 1
            else:
                projected_profit += profit

        active_features = [f for f in project.features if f.status != 'closed']
        closed_feature_count = sum(1 for f in project.features if f.status == 'closed')

        project_rows.append({
            'id': project.id,
            'name': project.name,
            'client_label': project.client_label,
            'colour': project.colour,
            'lifecycle': project.lifecycle,
            'dev_hours': round(dev_hours_by_project.get(project.id, 0.0), 2),
            'total_cost': summary['total_cost'],
            'client_charge': summary['client_charge'],
            'profit': profit,
            'active_feature_count': len(active_features),
            'closed_feature_count': closed_feature_count,
            'features': [
                {
                    'id': f.id,
                    'name': f.name,
                    'status': f.status,
                    'status_colour': DI_STAGE_COLOURS.get(f.status, 'oak'),
                    'status_label': stage_label(f.status, project.track),
                    'dev_hours': round(dev_hours_by_feature.get(f.id, 0.0), 2),
                }
                for f in active_features
            ],
        })

    period_label_primary, period_label_secondary = periods.format_period_label_parts(period_type, period_key)

    return {
        'period_type': period_type,
        'period_key': period_key,
        'period_label': periods.format_period_label(period_type, period_key),
        'period_label_primary': period_label_primary,
        'period_label_secondary': period_label_secondary,
        'total_cost': period_cost,
        'cost_type_labels': [_COST_TYPE_CAPTION_LABELS[t] for t in DI_COST_TYPES if t in cost_types_present],
        'closed_profit': closed_profit,
        'closed_project_count': closed_project_count,
        'projected_profit': projected_profit,
        'projects': project_rows,
    }


def _period_dev_hours(project_ids, period_start, period_end):
    """(hours-by-project-id, hours-by-feature-id) for dev_time entries
    dated inside [period_start, period_end] — separate from
    board_data.py::feature_logged_hours(), which is a lifetime total for
    the feature detail modal; this one is scoped to whatever window
    Performance is currently showing."""
    if not project_ids:
        return {}, {}
    rows = (
        db.session.query(DiCostEntry.di_project_id, DiCostEntry.di_feature_id, DiCostEntry.hours)
        .filter(
            DiCostEntry.type == 'dev_time',
            DiCostEntry.di_project_id.in_(project_ids),
            DiCostEntry.date >= period_start,
            DiCostEntry.date <= period_end,
        )
        .all()
    )
    by_project, by_feature = {}, {}
    for project_id, feature_id, hours in rows:
        hours = hours or 0.0
        by_project[project_id] = by_project.get(project_id, 0.0) + hours
        if feature_id is not None:
            by_feature[feature_id] = by_feature.get(feature_id, 0.0) + hours
    return by_project, by_feature


def _period_cost_types(project_ids, period_start, period_end):
    """Set of DiCostEntry.type values with at least one entry dated
    inside the window, across the projects that overlap it — feeds the
    'Total cost' card's caption (e.g. "dev, Claude, hardware, licensing"
    when all four show up, fewer names when they don't)."""
    if not project_ids:
        return set()
    rows = (
        db.session.query(DiCostEntry.type)
        .filter(
            DiCostEntry.di_project_id.in_(project_ids),
            DiCostEntry.date >= period_start,
            DiCostEntry.date <= period_end,
        )
        .distinct()
        .all()
    )
    return {row[0] for row in rows}


def _period_total_cost(project_ids, period_start, period_end):
    """Sum of every cost-ledger entry (any type) dated inside the
    window, across the projects that overlap it — the 'Total cost' stat
    card at the top of Performance. Unlike the per-project Cost column in
    the table (a lifetime running total, same in every period), this one
    genuinely is period-scoped: 'how much did we spend this
    week/month/quarter', not 'how much has this project cost overall'."""
    if not project_ids:
        return 0.0
    total = (
        db.session.query(func.coalesce(func.sum(DiCostEntry.amount), 0))
        .filter(
            DiCostEntry.di_project_id.in_(project_ids),
            DiCostEntry.date >= period_start,
            DiCostEntry.date <= period_end,
        )
        .scalar()
    )
    return float(total or 0)
