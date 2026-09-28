# The Incoming tray: promote a card to a feature, dismiss it, and the live card
# list. Each card is a shared FeatureRequest that DI does not own; see each
# route for how it is handled.
#
# Promote and dismiss return JSON. The JS reloads the page after a promote and
# re-fetches intake_cards_fragment after a dismiss.
#
# di_changes fires only for DI models, so a new FeatureRequest shows up on the
# next page load, not live.

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


def _missing_permanent_board_response():
    # FeatureRequest cards are filed on the permanent board; without it there
    # is nowhere to put the feature or the dismissal marker.
    return jsonify({'error': 'The permanent Digital Innovation board is missing. Ask an admin to restore it.'}), 409


@digital_innovation_bp.route('/feature-requests/<int:feature_request_id>/promote', methods=['POST'])
@login_required
def promote_feature_request(feature_request_id):
    """Creates a feature from a FeatureRequest and sets the request to
    'in_progress', which takes it off the tray. Logs and notifies the
    submitter the same way the feedback module's update_fr_status does."""
    _require_board_write_access()
    fr = FeatureRequest.query.filter_by(id=feature_request_id, status='requested').first()
    if not fr:
        abort(404)

    project = permanent_project()
    if not project:
        return _missing_permanent_board_response()

    feature = step_engine.create_feature(project, fr.title)

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
    """Hides a FeatureRequest from this tray only; the request itself stays
    'requested'. Records a 'dismissed' DiIntakeItem marker that
    pending_intake_items() skips. Idempotent: a repeat dismiss (double click,
    two tabs) finds the marker and adds no second row."""
    _require_board_write_access()
    fr = FeatureRequest.query.filter_by(id=feature_request_id, status='requested').first()
    if not fr:
        abort(404)

    already_dismissed = DiIntakeItem.query.filter_by(
        source_type='feature_request', source_ref=str(fr.id), status='dismissed',
    ).first()
    if already_dismissed:
        return jsonify({'id': fr.id, 'status': 'dismissed'})

    project = permanent_project()
    if not project:
        return _missing_permanent_board_response()

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
