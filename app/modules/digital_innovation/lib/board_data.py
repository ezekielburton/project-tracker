# Board page data assembly — kept separate from routes/board.py so a future
# JSON refresh endpoint (Phase 2f, driven by the di_changes SSE ping) can
# reuse the exact same query/shape a full page load uses, rather than two
# places independently deciding what a board "looks like".

from sqlalchemy import func
from app.modules.core.shared.extensions import db
from app.modules.digital_innovation.models import DiProject, DiFeature, DiCostEntry, DI_STAGES


def sidebar_projects():
    """Active DiProjects for the module's own sidebar — the permanent OVP
    board always leads the list, then whichever else exists by creation
    order (no manual reordering yet)."""
    return (
        DiProject.query
        .filter_by(lifecycle='active')
        .order_by(DiProject.is_permanent.desc(), DiProject.created_at.asc())
        .all()
    )


def default_project():
    """Landing project for a bare /digital-innovation visit — the
    permanent board, since it's guaranteed to exist (seeded by the
    migration and un-deletable)."""
    return (
        DiProject.query
        .filter_by(lifecycle='active')
        .order_by(DiProject.is_permanent.desc(), DiProject.created_at.asc())
        .first()
    )


def _feature_progress(feature):
    """(done, total, active_step_label, current_step_number, progress_pct)
    for a feature's CURRENT stage. feature.steps is already sorted by
    sort_order (see the relationship's order_by in models.py), so
    filtering it in Python keeps that order — no separate query needed.
    An empty or fully-ticked list just reports what it sees; Phase 2b's
    auto-advance logic is what keeps a feature from sitting on the board
    in that state for long.

    current_step_number is the same "Step N of total" position the board
    card's text has always shown (N = done+1 while a step is still open,
    or total once every step is done) — pulled out here, instead of
    staying an inline Jinja ternary, so the progress bar's fill width can
    share the exact same number the text uses rather than recomputing it
    a second time in the template."""
    stage_steps = [s for s in feature.steps if s.stage == feature.status]
    done = sum(1 for s in stage_steps if s.is_done)
    total = len(stage_steps)
    active = next((s for s in stage_steps if not s.is_done), None)
    current_step_number = (done + 1) if active else total
    progress_pct = round(100 * current_step_number / total) if total else 0
    return done, total, (active.title if active else None), current_step_number, progress_pct


def feature_logged_hours(feature_id):
    # Public (not board.py-private) — lib/feature_detail.py reuses this
    # exact query for the feature detail modal's "Nh logged" pill.
    total = (
        db.session.query(func.coalesce(func.sum(DiCostEntry.hours), 0))
        .filter(DiCostEntry.di_feature_id == feature_id, DiCostEntry.type == 'dev_time')
        .scalar()
    )
    return total or 0


def build_board_context(di_project):
    """Everything board.html needs to render one project's board: open
    features grouped into their 7 columns (each wrapped with its progress
    info) plus the closed-features strip."""
    open_features = (
        DiFeature.query
        .filter(DiFeature.di_project_id == di_project.id, DiFeature.status != 'closed')
        .order_by(DiFeature.sort_order)
        .all()
    )

    columns = {stage: [] for stage in DI_STAGES}
    for feature in open_features:
        done, total, active_label, current_step_number, progress_pct = _feature_progress(feature)
        columns.setdefault(feature.status, []).append({
            'feature': feature,
            'done': done,
            'total': total,
            'active_step_label': active_label,
            'current_step_number': current_step_number,
            'progress_pct': progress_pct,
            'logged_hours': feature_logged_hours(feature.id),
        })

    closed_features = (
        DiFeature.query
        .filter_by(di_project_id=di_project.id, status='closed')
        .order_by(DiFeature.closed_at.desc())
        .all()
    )

    return {
        'columns': columns,
        'closed_features': closed_features,
        'open_feature_count': len(open_features),
    }
