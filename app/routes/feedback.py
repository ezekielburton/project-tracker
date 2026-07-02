from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import FeatureRequest, FeatureRequestUpvote, FeatureRequestComment, BugReport, BugReportComment
from app.utils import get_actor, log_activity

feedback_bp = Blueprint('feedback', __name__)

VALID_STATUSES = {'requested', 'in_progress', 'testing', 'implemented'}


def _feature_dict(f):
    """Serialise a FeatureRequest for JSON embedding in templates."""
    return {
        'id':           f.id,
        'title':        f.title,
        'description':  f.description,
        'status':       f.status,
        'upvote_count': len(f.upvotes),
        'submitted_by': f.submitter.name,
        'created_at':   f.created_at.strftime('%d %b %Y'),
    }


# ── Index ─────────────────────────────────────────────────────────────────────
@feedback_bp.route('/feature-requests')
@login_required
def feature_requests():
    features = FeatureRequest.query.order_by(FeatureRequest.created_at.desc()).all()
    features_data = [_feature_dict(f) for f in features]
    return render_template('feedback/feature_requests.html', features_data=features_data)


# ── Load single feature (AJAX) ────────────────────────────────────────────────
@feedback_bp.route('/feature-requests/<int:feature_id>')
@login_required
def get_feature(feature_id):
    feature      = FeatureRequest.query.get_or_404(feature_id)
    comments     = FeatureRequestComment.query.filter_by(
        feature_id=feature_id, parent_id=None
    ).order_by(FeatureRequestComment.created_at.asc()).all()
    upvote_count = len(feature.upvotes)
    actor        = get_actor()
    user_upvoted = any(u.user_id == actor.id for u in feature.upvotes)
    return render_template('feedback/_feature_content.html',
                           feature=feature, comments=comments,
                           upvote_count=upvote_count, user_upvoted=user_upvoted,
                           actor=actor)


# ── Submit new feature request ────────────────────────────────────────────────
@feedback_bp.route('/feature-requests', methods=['POST'])
@login_required
def submit_feature():
    data        = request.get_json()
    title       = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    if not title or not description:
        return jsonify({'success': False, 'error': 'Title and description required'}), 400

    actor = get_actor()

    feature = FeatureRequest(
        title=title,
        description=description,
        submitted_by_id=actor.id,
        status='requested'
    )
    db.session.add(feature)
    db.session.commit()

    from app.notifications import notify_admin_of_new_feedback, create_notification
    from app.models import User as UserModel
    notify_admin_of_new_feedback(
        item_type='Feature Request',
        title=feature.title,
        submitted_by=actor,
        url_path=f'/feature-requests#fr-{feature.id}'
    )

    admin_user = UserModel.query.filter_by(role='admin').first()
    if admin_user and admin_user.id != actor.id:
        create_notification(
            recipient=admin_user,
            message=f'{actor.name} submitted a feature request: "{feature.title}"',
            notification_type='feature_request',
            triggered_by=actor,
            link=f'/feature-requests#fr-{feature.id}'
        )

    log_activity('feature_request_submitted', f'Feature request "{feature.title}" submitted by {actor.name}',
                 user=actor, entity_type='feature_request', entity_name=feature.title, entity_id=feature.id)

    return jsonify({'success': True, 'feature': _feature_dict(feature)})


# ── Toggle upvote ─────────────────────────────────────────────────────────────
@feedback_bp.route('/feature-requests/<int:feature_id>/upvote', methods=['POST'])
@login_required
def toggle_upvote(feature_id):
    actor = get_actor()

    existing = FeatureRequestUpvote.query.filter_by(
        feature_id=feature_id, user_id=actor.id
    ).first()

    if existing:
        db.session.delete(existing)
        voted = False
    else:
        db.session.add(FeatureRequestUpvote(feature_id=feature_id, user_id=actor.id))
        voted = True

    db.session.commit()
    count = FeatureRequestUpvote.query.filter_by(feature_id=feature_id).count()
    return jsonify({'success': True, 'voted': voted, 'count': count})


# ── Add comment ───────────────────────────────────────────────────────────────
@feedback_bp.route('/feature-requests/<int:feature_id>/comments', methods=['POST'])
@login_required
def add_fr_comment(feature_id):
    FeatureRequest.query.get_or_404(feature_id)
    body      = request.form.get('body', '').strip()
    parent_id = request.form.get('parent_id', type=int)
    if not body:
        return jsonify({'success': False, 'error': 'Body required'}), 400

    actor = get_actor()

    comment = FeatureRequestComment(
        feature_id=feature_id,
        user_id=actor.id,
        parent_id=parent_id,
        body=body
    )
    db.session.add(comment)
    db.session.commit()
    return jsonify({
        'success': True,
        'comment': {
            'id':            comment.id,
            'author':        actor.name,
            'avatar_letter': actor.name[0].upper(),
            'body':          comment.body,
            'created_at':    comment.created_at.strftime('%d %b %Y, %H:%M'),
            'parent_id':     comment.parent_id,
        }
    })


# ── Delete comment (admin) ────────────────────────────────────────────────────
@feedback_bp.route('/feature-requests/comments/<int:comment_id>', methods=['DELETE'])
@login_required
def delete_fr_comment(comment_id):
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    comment = FeatureRequestComment.query.get_or_404(comment_id)
    db.session.delete(comment)
    db.session.commit()
    return jsonify({'success': True})


# ── Update status (admin) ─────────────────────────────────────────────────────
@feedback_bp.route('/feature-requests/<int:feature_id>/status', methods=['PATCH'])
@login_required
def update_fr_status(feature_id):
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    feature    = FeatureRequest.query.get_or_404(feature_id)
    data       = request.get_json()
    new_status = data.get('status')
    if new_status not in VALID_STATUSES:
        return jsonify({'success': False, 'error': 'Invalid status'}), 400
    old_status     = feature.status
    feature.status = new_status
    db.session.commit()

    log_activity('feature_request_status_changed',
                 f'Feature request "{feature.title}" status changed from {old_status} to {new_status}',
                 user=current_user, entity_type='feature_request', entity_name=feature.title, entity_id=feature.id)

    # Notify the creator on meaningful status changes
    if new_status in ('in_progress', 'implemented') and feature.submitter:
        from app.notifications import create_notification
        messages = {
            'in_progress': f'Your feature request "{feature.title}" is now in progress.',
            'implemented': f'Your feature request "{feature.title}" has been implemented!',
        }
        create_notification(
            recipient=feature.submitter,
            message=messages[new_status],
            notification_type='feature_status',
            triggered_by=current_user
        )

    return jsonify({'success': True, 'status': feature.status})


# ── Delete feature (admin or creator) ────────────────────────────────────────
@feedback_bp.route('/feature-requests/<int:feature_id>', methods=['DELETE'])
@login_required
def delete_feature(feature_id):
    feature = FeatureRequest.query.get_or_404(feature_id)
    actor   = get_actor()
    if current_user.role != 'admin' and actor.id != feature.submitted_by_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    title = feature.title
    db.session.delete(feature)
    db.session.commit()
    log_activity('feature_request_deleted', f'Feature request "{title}" deleted by {actor.name}',
                 user=actor, entity_type='feature_request', entity_name=title)
    return jsonify({'success': True})


# ════════════════════════════════════════════════════════════════════════════════
# BUG REPORTS
# ════════════════════════════════════════════════════════════════════════════════

BUG_VALID_STATUSES = {'in_queue', 'fix_in_progress', 'testing', 'resolved'}


def _bug_dict(b):
    """Serialise a BugReport for JSON embedding in templates."""
    return {
        'id':           b.id,
        'title':        b.title,
        'description':  b.description,
        'status':       b.status,
        'submitted_by': b.submitter.name,
        'created_at':   b.created_at.strftime('%d %b %Y'),
    }


# ── Index ─────────────────────────────────────────────────────────────────────
@feedback_bp.route('/bug-reports')
@login_required
def bug_reports():
    bugs      = BugReport.query.order_by(BugReport.created_at.desc()).all()
    bugs_data = [_bug_dict(b) for b in bugs]
    return render_template('feedback/bug_reports.html', bugs_data=bugs_data)


# ── Load single bug (AJAX) ────────────────────────────────────────────────────
@feedback_bp.route('/bug-reports/<int:bug_id>')
@login_required
def get_bug(bug_id):
    bug      = BugReport.query.get_or_404(bug_id)
    comments = BugReportComment.query.filter_by(
        bug_id=bug_id, parent_id=None
    ).order_by(BugReportComment.created_at.asc()).all()
    actor    = get_actor()
    return render_template('feedback/_bug_content.html',
                           bug=bug, comments=comments, actor=actor)


# ── Submit new bug report ─────────────────────────────────────────────────────
@feedback_bp.route('/bug-reports', methods=['POST'])
@login_required
def submit_bug():
    data        = request.get_json()
    title       = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    if not title or not description:
        return jsonify({'success': False, 'error': 'Title and description required'}), 400

    actor = get_actor()
    bug   = BugReport(
        title=title,
        description=description,
        submitted_by_id=actor.id,
        status='in_queue'
    )
    db.session.add(bug)
    db.session.commit()

    from app.notifications import notify_admin_of_new_feedback, create_notification
    from app.models import User as UserModel
    notify_admin_of_new_feedback(
        item_type='Bug Report',
        title=bug.title,
        submitted_by=actor,
        url_path=f'/bug-reports#br-{bug.id}'
    )

    admin_user = UserModel.query.filter_by(role='admin').first()
    if admin_user and admin_user.id != actor.id:
        create_notification(
            recipient=admin_user,
            message=f'{actor.name} reported a bug: "{bug.title}"',
            notification_type='bug_report',
            triggered_by=actor,
            link=f'/bug-reports#br-{bug.id}'
        )

    log_activity('bug_report_submitted', f'Bug report "{bug.title}" submitted by {actor.name}',
                 user=actor, entity_type='bug_report', entity_name=bug.title, entity_id=bug.id)

    return jsonify({'success': True, 'bug': _bug_dict(bug)})


# ── Update status (admin) ─────────────────────────────────────────────────────
@feedback_bp.route('/bug-reports/<int:bug_id>/status', methods=['PATCH'])
@login_required
def update_bug_status(bug_id):
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    bug        = BugReport.query.get_or_404(bug_id)
    data       = request.get_json()
    new_status = data.get('status')
    if new_status not in BUG_VALID_STATUSES:
        return jsonify({'success': False, 'error': 'Invalid status'}), 400
    old_status = bug.status
    bug.status = new_status
    db.session.commit()

    log_activity('bug_report_status_changed',
                 f'Bug report "{bug.title}" status changed from {old_status} to {new_status}',
                 user=current_user, entity_type='bug_report', entity_name=bug.title, entity_id=bug.id)

    # Notify creator on meaningful status changes
    if new_status in ('fix_in_progress', 'resolved') and bug.submitter:
        from app.notifications import create_notification
        messages = {
            'fix_in_progress': f'Your bug report "{bug.title}" is now being worked on.',
            'resolved':        f'Your bug report "{bug.title}" has been resolved.',
        }
        create_notification(
            recipient=bug.submitter,
            message=messages[new_status],
            notification_type='bug_status',
            triggered_by=current_user
        )

    return jsonify({'success': True, 'status': bug.status})


# ── Add comment ───────────────────────────────────────────────────────────────
@feedback_bp.route('/bug-reports/<int:bug_id>/comments', methods=['POST'])
@login_required
def add_bug_comment(bug_id):
    BugReport.query.get_or_404(bug_id)
    body      = request.form.get('body', '').strip()
    parent_id = request.form.get('parent_id', type=int)
    if not body:
        return jsonify({'success': False, 'error': 'Body required'}), 400

    actor   = get_actor()
    comment = BugReportComment(
        bug_id=bug_id,
        user_id=actor.id,
        parent_id=parent_id,
        body=body
    )
    db.session.add(comment)
    db.session.commit()
    return jsonify({
        'success': True,
        'comment': {
            'id':            comment.id,
            'author':        actor.name,
            'avatar_letter': actor.name[0].upper(),
            'body':          comment.body,
            'created_at':    comment.created_at.strftime('%d %b %Y, %H:%M'),
            'parent_id':     comment.parent_id,
        }
    })


# ── Delete comment (admin) ────────────────────────────────────────────────────
@feedback_bp.route('/bug-reports/comments/<int:comment_id>', methods=['DELETE'])
@login_required
def delete_bug_comment(comment_id):
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    comment = BugReportComment.query.get_or_404(comment_id)
    db.session.delete(comment)
    db.session.commit()
    return jsonify({'success': True})


# ── Delete bug (admin or creator) ─────────────────────────────────────────────
@feedback_bp.route('/bug-reports/<int:bug_id>', methods=['DELETE'])
@login_required
def delete_bug(bug_id):
    bug   = BugReport.query.get_or_404(bug_id)
    actor = get_actor()
    if current_user.role != 'admin' and actor.id != bug.submitted_by_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    title = bug.title
    db.session.delete(bug)
    db.session.commit()
    log_activity('bug_report_deleted', f'Bug report "{title}" deleted by {actor.name}',
                 user=actor, entity_type='bug_report', entity_name=title)
    return jsonify({'success': True})
