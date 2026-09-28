# Board-page data, shared by the full page and the live-refresh fragments.

from collections import namedtuple

from sqlalchemy import func
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import FeatureRequest
from app.modules.digital_innovation.models import DiProject, DiFeature, DiCostEntry, DiIntakeItem, DI_STAGES


def sidebar_projects():
    """Active DiProjects for the module sidebar — permanent OVP board first,
    then others by creation order."""
    return (
        DiProject.query
        .filter_by(lifecycle='active')
        .order_by(DiProject.is_permanent.desc(), DiProject.created_at.asc())
        .all()
    )


def default_project():
    """Landing board for a bare /digital-innovation visit: the permanent
    board, which the migration seeds."""
    return (
        DiProject.query
        .filter_by(lifecycle='active')
        .order_by(DiProject.is_permanent.desc(), DiProject.created_at.asc())
        .first()
    )


def closed_projects():
    """Projects on the Archive 'Closed' list, most recently closed first."""
    return (
        DiProject.query
        .filter_by(lifecycle='closed')
        .order_by(DiProject.closed_at.desc())
        .all()
    )


def archived_projects():
    """Projects on the Archive 'Archived' list, most recently closed first."""
    return (
        DiProject.query
        .filter_by(lifecycle='archived')
        .order_by(DiProject.closed_at.desc())
        .all()
    )


def permanent_project():
    """The seeded OVP board, where all intake items are filed. Resolves to
    the same row as default_project(), which answers a different question."""
    return DiProject.query.filter_by(is_permanent=True).first()


# One Incoming-tray card, built from a shared FeatureRequest; id is its id.
IncomingCard = namedtuple('IncomingCard', ['id', 'title', 'source_label', 'description'])


def pending_intake_items(di_project):
    """IncomingCards for di_project's tray, oldest first: on the permanent
    board only, FeatureRequests in status 'requested'. A dismissed request
    is hidden by a 'dismissed' DiIntakeItem marker; the FeatureRequest
    itself is left untouched. Other boards get an empty list."""
    if not di_project.is_permanent:
        return []

    dismissed_fr_ids = {
        int(row.source_ref) for row in
        DiIntakeItem.query.filter_by(source_type='feature_request', status='dismissed').all()
        if row.source_ref and row.source_ref.isdigit()
    }
    requests = (FeatureRequest.query
                .filter_by(status='requested')
                .order_by(FeatureRequest.created_at.asc(), FeatureRequest.id.asc())
                .all())
    return [
        IncomingCard(fr.id, fr.title, 'Feature request · ' + fr.submitter.name, fr.description)
        for fr in requests if fr.id not in dismissed_fr_ids
    ]


def _feature_progress(feature):
    """(done, total, active_step_label, current_step_number, progress_pct) for
    the current stage. current_step_number is done+1 while a step is open,
    else total; the progress bar and "Step N of M" text both use it."""
    stage_steps = [s for s in feature.steps if s.stage == feature.status]
    done = sum(1 for s in stage_steps if s.is_done)
    total = len(stage_steps)
    active = next((s for s in stage_steps if not s.is_done), None)
    current_step_number = (done + 1) if active else total
    progress_pct = round(100 * current_step_number / total) if total else 0
    return done, total, (active.title if active else None), current_step_number, progress_pct


def feature_logged_hours(feature_id):
    # Lifetime dev_time hours for a feature. Also used by lib/feature_detail.py.
    total = (
        db.session.query(func.coalesce(func.sum(DiCostEntry.hours), 0))
        .filter(DiCostEntry.di_feature_id == feature_id, DiCostEntry.type == 'dev_time')
        .scalar()
    )
    return total or 0


def build_board_context(di_project):
    """Board context for one project: open features grouped into their stage
    columns with progress info, plus the closed features."""
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
