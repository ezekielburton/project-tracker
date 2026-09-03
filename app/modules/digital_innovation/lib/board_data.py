# Board-page data assembly, separate from routes/board.py so a JSON refresh
# endpoint can reuse the same query/shape as a full page load.

from collections import namedtuple

from sqlalchemy import func
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import FeatureRequest
from app.modules.digital_innovation.models import DiProject, DiFeature, DiCostEntry, DiIntakeItem, DI_STAGES

# One shape for both Incoming-tray sources: a native DiIntakeItem
# (kind='intake_item') and a live FeatureRequest (kind='feature_request').
# `id` is the underlying row's id; promote/dismiss in routes/intake.py branch
# by kind — a FeatureRequest is a shared record DI doesn't own, a DiIntakeItem
# is DI's own row.


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
    """Landing project for a bare /digital-innovation visit — the permanent
    board (guaranteed to exist, seeded and un-deletable)."""
    return (
        DiProject.query
        .filter_by(lifecycle='active')
        .order_by(DiProject.is_permanent.desc(), DiProject.created_at.asc())
        .first()
    )


def closed_projects():
    """Projects on the Archive 'Closed' list — off the active sidebar, still
    viewable, reopenable, or archivable one step further."""
    return (
        DiProject.query
        .filter_by(lifecycle='closed')
        .order_by(DiProject.closed_at.desc())
        .all()
    )


def archived_projects():
    """Projects on the Archive 'Archived' list — one step past closed,
    reopenable the same way."""
    return (
        DiProject.query
        .filter_by(lifecycle='archived')
        .order_by(DiProject.closed_at.desc())
        .all()
    )


def permanent_project():
    """The un-deletable seeded OVP board — the only project the Incoming tray
    attaches intake items to. Kept separate from default_project() (which means
    "where a bare visit lands") even though both resolve to the same row."""
    return DiProject.query.filter_by(is_permanent=True).first()


IncomingCard = namedtuple('IncomingCard', ['kind', 'id', 'title', 'source_label', 'description'])


def pending_intake_items(di_project):
    """Cards for di_project's Incoming tray, oldest first (a queue). Merges two
    sources by arrival time:

    1. Native DiIntakeItem rows with status='pending' (filed by
       services/intake.py::add_feedback_item() for non-FeatureRequest sources).
    2. Live FeatureRequest rows with status='requested' — read straight off the
       shared table so every existing and new submission shows up. DI never
       mutates that shared row to hide a card: a dismissed request is tracked by
       a marker DiIntakeItem (source_type='feature_request', status='dismissed')
       excluded below, leaving the request itself untouched. Promoting sets the
       FeatureRequest to 'in_progress', which removes it from this list directly.

    Only the permanent board surfaces FeatureRequest cards."""
    entries = []  # (created_at, IncomingCard) pairs, sorted together at the end

    native = DiIntakeItem.query.filter_by(di_project_id=di_project.id, status='pending').all()
    for item in native:
        source_label = item.source_type + (' · ' + item.source_ref if item.source_ref else '')
        entries.append((
            item.created_at,
            IncomingCard('intake_item', item.id, item.title, source_label, item.description),
        ))

    if di_project.is_permanent:
        dismissed_fr_ids = {
            int(row.source_ref) for row in
            DiIntakeItem.query.filter_by(source_type='feature_request', status='dismissed').all()
            if row.source_ref and row.source_ref.isdigit()
        }
        for fr in FeatureRequest.query.filter_by(status='requested').all():
            if fr.id in dismissed_fr_ids:
                continue
            entries.append((
                fr.created_at,
                IncomingCard('feature_request', fr.id, fr.title, 'Feature request · ' + fr.submitter.name, fr.description),
            ))

    entries.sort(key=lambda pair: pair[0])
    return [card for _, card in entries]


def _feature_progress(feature):
    """(done, total, active_step_label, current_step_number, progress_pct) for a
    feature's current stage. feature.steps is pre-sorted by sort_order, so the
    Python filter preserves order. current_step_number is done+1 while a step is
    open, or total once all are done — computed here so the progress bar and the
    "Step N of total" text share one number."""
    stage_steps = [s for s in feature.steps if s.stage == feature.status]
    done = sum(1 for s in stage_steps if s.is_done)
    total = len(stage_steps)
    active = next((s for s in stage_steps if not s.is_done), None)
    current_step_number = (done + 1) if active else total
    progress_pct = round(100 * current_step_number / total) if total else 0
    return done, total, (active.title if active else None), current_step_number, progress_pct


def feature_logged_hours(feature_id):
    # Public — lib/feature_detail.py reuses this for the modal's "Nh logged" pill.
    total = (
        db.session.query(func.coalesce(func.sum(DiCostEntry.hours), 0))
        .filter(DiCostEntry.di_feature_id == feature_id, DiCostEntry.type == 'dev_time')
        .scalar()
    )
    return total or 0


def build_board_context(di_project):
    """Everything board.html needs for one project: open features grouped into
    their 7 columns (each with progress info) plus the closed-features strip."""
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
