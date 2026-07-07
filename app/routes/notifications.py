from flask import Blueprint, jsonify, request, url_for
from flask_login import login_required, current_user
from app import db
from app.models import Notification
from datetime import datetime

notifications_bp = Blueprint('notifications', __name__)


@notifications_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_read(notification_id):
    """
    Mark a single notification as read.
    Returns JSON with the URL to navigate to (the related project).
    """
    from flask import session
    notification = Notification.query.get_or_404(notification_id)

    # Emulation-aware auth check — same pattern as archive/restore routes
    emulating_id = session.get('emulating_user_id')
    notif_user_id = emulating_id if (emulating_id and current_user.role == 'admin') else current_user.id

    if notification.recipient_id != notif_user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    notification.is_read = True
    db.session.commit()

    # Build the URL to redirect the user to
    # Prefer an explicit link (blog posts, feature requests, bug reports),
    # then fall back to the related project, then home.
    if notification.link:
        redirect_url = notification.link
    elif notification.project_id:
        redirect_url = url_for('project_detail.detail', project_id=notification.project_id)
    else:
        redirect_url = url_for('main.index')

    return jsonify({
        'success': True,
        'redirect_url': redirect_url
    })


@notifications_bp.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_read():
    """
    Mark every unread notification for the current user as read.
    """
    Notification.query.filter_by(
        recipient_id=current_user.id,
        is_read=False
    ).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})

@notifications_bp.route('/notifications/<int:notification_id>/archive', methods=['POST'])
@login_required
def archive_notification(notification_id):
    from flask import session
    # Fetch the notification or return 404 if it doesn't exist
    notification = Notification.query.get_or_404(notification_id)


    # Emulation-aware auth check:
    # If admin is emulating another user, check against the emulated user's ID
    # Otherwise, check against the real logged-in user's ID
    emulating_id = session.get('emulating_user_id')
    notif_user_id = emulating_id if (emulating_id and current_user.role == 'admin') else current_user.id

    # Block access if this notification doesn't belong to the resolved user
    if notification.recipient_id != notif_user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    # Mark the notification as archived and also read
    notification.is_archived = True
    notification.is_read = True
    db.session.commit()

    return jsonify({'success': True})


@notifications_bp.route('/notifications/archive-all', methods=['POST'])
@login_required
def archive_all():
    from flask import session
    emulating_id = session.get('emulating_user_id')
    notif_user_id = emulating_id if (emulating_id and current_user.role == 'admin') else current_user.id
    Notification.query.filter_by(
        recipient_id=notif_user_id,
        is_archived=False
    ).update({'is_archived': True, 'is_read': True})
    db.session.commit()
    return jsonify({'success': True})


@notifications_bp.route('/notifications/delete-bulk', methods=['POST'])
@login_required
def delete_bulk():
    from flask import session
    data = request.get_json()
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'success': False, 'error': 'No IDs Provided'}), 400
    emulating_id = session.get('emulating_user_id')
    notif_user_id = emulating_id if (emulating_id and current_user.role == 'admin') else current_user.id
    Notification.query.filter(
        Notification.id.in_(ids),
        Notification.recipient_id == notif_user_id
    ).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({'success': True})

@notifications_bp.route('/notifications/poll')
@login_required
def poll():
    """
    Lightweight polling endpoint.
    Accepts a 'since' query param (ISO timestamp).
    Returns any unread, non-archived notifications created after that time.
    JS calls this every 30s and uses the results to fire desktop notifications + sound.
    """
    from flask import session
    emulating_id = session.get('emulating_user_id')
    notif_user_id = emulating_id if (emulating_id and current_user.role == 'admin') else current_user.id

    since_str = request.args.get('since')
    query = Notification.query.filter_by(
        recipient_id=notif_user_id,
        is_archived=False,
        is_read=False
    )
    if since_str:
        try:
            since_dt = datetime.fromisoformat(since_str)
            query = query.filter(Notification.created_at > since_dt)
        except ValueError:
            pass  # bad timestamp — return all unread, not a fatal error

    new_notifications = query.order_by(Notification.created_at.asc()).all()

    from datetime import timezone, timedelta
    dubai_tz = timezone(timedelta(hours=4))

    def _fmt(dt):
        return dt.replace(tzinfo=timezone.utc).astimezone(dubai_tz).strftime('%d %b %Y, %H:%M')

    return jsonify({
        'notifications': [
            {
                'id': n.id,
                'message': n.message,
                'notification_type': n.notification_type,
                'created_at': n.created_at.isoformat(),
                'time_display': _fmt(n.created_at)
            }
            for n in new_notifications
        ]
    })


#Restore Notifications Route
@notifications_bp.route('/notifications/<int:notification_id>/restore', methods=['POST'])
@login_required
def restore_notification(notification_id):
    from flask import session

    # Fetch the notification or return 404 if it doesn't exist
    notification = Notification.query.get_or_404(notification_id)

    # Emulation-aware auth check - same pattern as archive route
    emulating_id = session.get('emulating_user_id')
    notif_user_id = emulating_id if (emulating_id and current_user.role == 'admin') else current_user.id

    # Block access if this notification doesn't belong to the resolved user
    if notification.recipient_id != notif_user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    # Move notification back to inbox
    notification.is_archived = False
    db.session.commit()

    return jsonify({'success': True})

