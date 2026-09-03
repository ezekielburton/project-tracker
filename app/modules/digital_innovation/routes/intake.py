# The Incoming overlay: promote a card into a real feature, dismiss it, and
# refresh the card list live. A card is one of two kinds (see board_data.py's
# IncomingCard/pending_intake_items), each with its own promote/dismiss pair:
#
# - /intake/<id>/... — a native DiIntakeItem, DI's own row. Promote/dismiss
#   flips its status.
# - /feature-requests/<id>/... — a live FeatureRequest, the shared feature-idea
#   table DI doesn't own, so promote/dismiss can't just flip a flag on it — see
#   each route's docstring for what it does instead.
#
# Both promote routes call step_engine.create_feature, so a promoted card starts
# on the board identically to a hand-typed one. None of the four hand back a
# fragment — each changes more than the overlay (a promote also adds a card and
# shifts the active-feature count), so the JS does a full reload.
#
# intake_cards_fragment is what digital_innovation_board.js re-fetches when the
# di_changes SSE channel pings, keeping the Incoming badge and open overlay live
# from the same _incoming_cards.html partial board.html's initial render uses.
# Note: di_changes fires only for DI's own watched models, so a brand-new
# FeatureRequest submission appears only on the next full page load, not live.

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

    # item.description isn't carried over — DiFeature has no description field.
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
    like any other promote, AND sets the feature request itself to 'in_progress'
    — that's what removes it from pending_intake_items() (a FeatureRequest shows
    up there only while status='requested'), reusing the same notification the
    app sends for that status change (routes/feedback.py's update_fr_status)."""
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
    only. The feature request itself is untouched — still 'requested', still
    visible/upvotable/commentable on the public Feature Requests page (dismissing
    here is DI saying "not right now," not the app saying "no"). Recorded as a
    DiIntakeItem(source_type='feature_request', status='dismissed') purely so
    pending_intake_items() knows to skip this fr.id next time."""
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
