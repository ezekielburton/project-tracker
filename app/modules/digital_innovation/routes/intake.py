# Digital Innovation — the Incoming overlay: promote a card into a real
# feature, dismiss it outright, and (1 Sep 2026) refresh the overlay's
# card list live. A card is one of two kinds (see board_data.py's
# IncomingCard/pending_intake_items) — this file has a separate
# promote/dismiss pair for each:
#
# - /intake/<id>/... — a native DiIntakeItem, DI's own row (the seam for
#   a future non-FeatureRequest source). Promote/dismiss just flips its
#   status.
# - /feature-requests/<id>/... — a live FeatureRequest, the shared,
#   already-existing "someone submitted a feature idea" table (2 Sep
#   2026, per Ezekiel: the tray should show those too, old and new, not
#   just items explicitly filed through the DI-only seam). DI doesn't
#   own that row, so promote/dismiss can't just flip an is-this-DI's-
#   problem flag on it the way a DiIntakeItem's status can — see each
#   route's own docstring for what each action does instead.
#
# Both promote routes call step_engine.create_feature — the exact same
# call the "+ Add feature" button makes, so a promoted card starts life
# on the board identically to a hand-typed one. None of the four routes
# hand back a fragment — all of them change more than the overlay itself
# (a promote also adds a card to a column and shifts the header's
# "X active features" count), so the JS side does a full reload rather
# than patching pieces of the DOM.
#
# intake_cards_fragment below is different: it's what
# digital_innovation_board.js re-fetches when the di_changes SSE channel
# pings, so the Incoming button's badge and, if it's open, the overlay
# itself stay live without a full page reload. Renders from the same
# _incoming_cards.html partial board.html's own initial render includes —
# one template, two callers, same shape as _feature_detail.html. Note:
# di_changes only fires for DI's OWN watched models (live_events.py) —
# a brand new FeatureRequest submission does NOT currently trigger this
# ping, so the live badge picks up new DiIntakeItem arrivals immediately
# but a newly-submitted feature request only appears on the next full
# page load/reload. Flagged here rather than solved now — wiring
# FeatureRequest into di_changes would mean giving live_events.py (which
# deliberately avoids importing model classes, matching by class name
# only) a way to resolve "which di_project's tray does this belong to"
# for a model with no di_project_id at all, which is more than this
# chunk asked for.

from flask import jsonify, abort, render_template
from flask_login import login_required, current_user

from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import FeatureRequest
from app.modules.core.shared.lib.utils import log_activity
from app.modules.core.shared.services.notifications import create_notification
from app.modules.digital_innovation.routes.blueprint import digital_innovation_bp
from app.modules.digital_innovation.models import DiProject, DiIntakeItem
from app.modules.digital_innovation.lib import step_engine
from app.modules.digital_innovation.lib.access import can_edit_di_board
from app.modules.digital_innovation.lib.board_data import pending_intake_items, permanent_project


def _require_board_write_access():
    if not can_edit_di_board(current_user):
        abort(403)


@digital_innovation_bp.route('/intake/<int:item_id>/promote', methods=['POST'])
@login_required
def promote_intake_item(item_id):
    _require_board_write_access()
    item = DiIntakeItem.query.filter_by(id=item_id, status='pending').first()
    if not item:
        abort(404)

    # item.description is deliberately not carried over — DiFeature has
    # no description field, and Ezekiel confirmed dropping it rather than
    # adding one just for this (28 Aug 2026).
    feature = step_engine.create_feature(item.project, item.title)
    item.status = 'promoted'
    db.session.commit()

    return jsonify({'id': item.id, 'status': item.status, 'feature_id': feature.id})


@digital_innovation_bp.route('/intake/<int:item_id>/dismiss', methods=['POST'])
@login_required
def dismiss_intake_item(item_id):
    _require_board_write_access()
    item = DiIntakeItem.query.filter_by(id=item_id, status='pending').first()
    if not item:
        abort(404)

    item.status = 'dismissed'
    db.session.commit()

    return jsonify({'id': item.id, 'status': item.status})


@digital_innovation_bp.route('/feature-requests/<int:feature_request_id>/promote', methods=['POST'])
@login_required
def promote_feature_request(feature_request_id):
    """Promotes a live FeatureRequest card. Creates the DI feature exactly
    like any other promote, AND sets the feature request itself to
    'in_progress' — per Ezekiel (2 Sep 2026): that's what actually
    removes it from pending_intake_items() (a FeatureRequest only shows
    up there while status='requested'), and it reuses the exact
    notification the app already sends for that status change (routes/
    feedback.py's update_fr_status), so the submitter hears "now in
    progress" the same way they would if an admin had changed it by hand
    on the Feature Requests page."""
    _require_board_write_access()
    fr = FeatureRequest.query.filter_by(id=feature_request_id, status='requested').first()
    if not fr:
        abort(404)

    feature = step_engine.create_feature(permanent_project(), fr.title)

    old_status = fr.status
    fr.status = 'in_progress'
    db.session.commit()

    log_activity('feature_request_status_changed',
                 f'Feature request "{fr.title}" status changed from {old_status} to {fr.status}',
                 user=current_user, entity_type='feature_request', entity_name=fr.title, entity_id=fr.id)

    if fr.submitter:
        create_notification(
            recipient=fr.submitter,
            message=f'Your feature request "{fr.title}" is now in progress.',
            notification_type='feature_status',
            triggered_by=current_user,
        )

    return jsonify({'id': fr.id, 'status': fr.status, 'feature_id': feature.id})


@digital_innovation_bp.route('/feature-requests/<int:feature_request_id>/dismiss', methods=['POST'])
@login_required
def dismiss_feature_request(feature_request_id):
    """Dismisses a live FeatureRequest card — hides it from THIS tray
    only. The feature request itself is untouched: still 'requested',
    still visible/upvotable/commentable on the public Feature Requests
    page, exactly as before (per Ezekiel, 2 Sep 2026 — dismissing here
    is DI saying "not right now," not the app saying "no"). Recorded as
    a DiIntakeItem(source_type='feature_request', status='dismissed')
    purely so pending_intake_items() knows to skip this fr.id next
    time — that row otherwise has no life of its own."""
    _require_board_write_access()
    fr = FeatureRequest.query.get_or_404(feature_request_id)

    project = permanent_project()
    dismissal = DiIntakeItem(
        di_project_id=project.id,
        source_type='feature_request',
        source_ref=str(fr.id),
        title=fr.title,
        status='dismissed',
    )
    db.session.add(dismissal)
    db.session.commit()

    return jsonify({'id': fr.id, 'status': 'dismissed'})


@digital_innovation_bp.route('/<int:di_project_id>/intake/cards')
@login_required
def intake_cards_fragment(di_project_id):
    _require_board_write_access()
    project = DiProject.query.get_or_404(di_project_id)
    return render_template(
        'digital_innovation/_incoming_cards.html',
        pending_intake_items=pending_intake_items(project),
        can_edit_board=can_edit_di_board(current_user),
    )
