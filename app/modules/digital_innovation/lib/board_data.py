# Board page data assembly — kept separate from routes/board.py so a future
# JSON refresh endpoint (Phase 2f, driven by the di_changes SSE ping) can
# reuse the exact same query/shape a full page load uses, rather than two
# places independently deciding what a board "looks like".

from collections import namedtuple

from sqlalchemy import func
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import FeatureRequest
from app.modules.digital_innovation.models import DiProject, DiFeature, DiCostEntry, DiIntakeItem, DI_STAGES

# One shape for both kinds of thing the Incoming tray can show — a native
# DiIntakeItem (kind='intake_item', a future non-FeatureRequest source
# like Slack) and a live FeatureRequest (kind='feature_request', the
# app's existing submit-a-feature-request flow). `id` is the underlying
# row's own id either way; routes/intake.py's promote/dismiss routes are
# split by kind because the two need genuinely different handling — a
# FeatureRequest is a shared, user-visible record DI doesn't own, a
# DiIntakeItem is DI's own row. See pending_intake_items() below.


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


def closed_projects():
    """Projects on the Archive screen's 'Closed' list — dropped off the
    active sidebar, still viewable there, reopenable, or archivable one
    step further."""
    return (
        DiProject.query
        .filter_by(lifecycle='closed')
        .order_by(DiProject.closed_at.desc())
        .all()
    )


def archived_projects():
    """Projects fully retired to the Archive screen's 'Archived' list —
    one step past closed, still reopenable the same way a closed project
    is."""
    return (
        DiProject.query
        .filter_by(lifecycle='archived')
        .order_by(DiProject.closed_at.desc())
        .all()
    )


def permanent_project():
    """The one un-deletable, seeded OVP board — the only project the
    Incoming tray (routes/board.py, board.html) ever attaches pending
    intake items to. Separate from default_project() even though they'd
    return the same row today: default_project() is "whatever a bare
    /digital-innovation visit should land on" and just happens to be the
    permanent board because of the sidebar_projects() ordering, while
    this one specifically means "the permanent board, because that's
    where intake items live" — the two reasons shouldn't be tangled
    together even though they resolve to the same query right now."""
    return DiProject.query.filter_by(is_permanent=True).first()


IncomingCard = namedtuple('IncomingCard', ['kind', 'id', 'title', 'source_label', 'description'])


def pending_intake_items(di_project):
    """Cards for di_project's Incoming tray, oldest first (a queue, not a
    feed) — board.html shows this only when di_project.is_permanent, but
    this function itself doesn't need to know that; it just answers
    "what's pending for this project."

    Two sources, merged and sorted together by when each one arrived:

    1. Native DiIntakeItem rows still `status='pending'` — the seam
       services/intake.py::add_feedback_item() files into, for whatever
       non-FeatureRequest source shows up later (a Slack bot, say).
    2. Live FeatureRequest rows still `status='requested'` (2 Sep 2026,
       per Ezekiel: "it should show all pending feature requests...
       already in the system... and all new ones that come in") — read
       straight off the shared feature-requests table rather than
       waiting for something to copy them into a DiIntakeItem first, so
       every existing and future submission just shows up on its own.
       DI never mutates that shared row just to hide a card here: a
       dismissed FeatureRequest is tracked with a DiIntakeItem
       (source_type='feature_request', source_ref=str(fr.id),
       status='dismissed') that only ever exists to be excluded below —
       the feature request itself stays exactly as it was, still visible
       and upvotable on its own page. Promoting, by contrast, DOES touch
       the FeatureRequest (routes/intake.py sets it to 'in_progress'),
       which is what actually removes it from `status='requested'` and
       therefore from this list — no dismissal record needed for that
       path.

    Only the permanent board ever surfaces FeatureRequest cards, since
    that's the only board with an Incoming tray at all."""
    entries = []  # list of (created_at, IncomingCard) — sorted once, together, at the end

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
