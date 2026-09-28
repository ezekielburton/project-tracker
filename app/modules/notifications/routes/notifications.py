from flask import Blueprint, jsonify, request, url_for
from flask_login import login_required
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import Notification
from app.modules.core.shared.lib.capabilities import effective_user
from datetime import datetime

notifications_bp = Blueprint('notifications', __name__)


@notifications_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_read(notification_id):
    """Marks one notification read and returns the URL to open: its link,
    else its project, else home."""
    notification = Notification.query.get_or_404(notification_id)

    # Emulation-aware: check against the emulated user when an admin emulates.
    notif_user_id = effective_user().id

    if notification.recipient_id != notif_user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    notification.is_read = True
    db.session.commit()

    if notification.link:
        redirect_url = notification.link
    elif notification.project_id:
        redirect_url = url_for('project_list.index', project=notification.project_id)
    else:
        redirect_url = url_for('main.index')

    return jsonify({
        'success': True,
        'redirect_url': redirect_url
    })


@notifications_bp.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_read():
    """Marks every unread notification as read for the effective user (the
    emulated user while an admin emulates), like the other routes here."""
    Notification.query.filter_by(
        recipient_id=effective_user().id,
        is_read=False
    ).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})

@notifications_bp.route('/notifications/<int:notification_id>/archive', methods=['POST'])
@login_required
def archive_notification(notification_id):
    notification = Notification.query.get_or_404(notification_id)


    # Emulation-aware ownership check, as in mark_read.
    notif_user_id = effective_user().id

    if notification.recipient_id != notif_user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    notification.is_archived = True
    notification.is_read = True
    db.session.commit()

    return jsonify({'success': True})


@notifications_bp.route('/notifications/archive-all', methods=['POST'])
@login_required
def archive_all():
    notif_user_id = effective_user().id
    Notification.query.filter_by(
        recipient_id=notif_user_id,
        is_archived=False
    ).update({'is_archived': True, 'is_read': True})
    db.session.commit()
    return jsonify({'success': True})


@notifications_bp.route('/notifications/delete-bulk', methods=['POST'])
@login_required
def delete_bulk():
    data = request.get_json()
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'success': False, 'error': 'No IDs Provided'}), 400
    notif_user_id = effective_user().id
    Notification.query.filter(
        Notification.id.in_(ids),
        Notification.recipient_id == notif_user_id
    ).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({'success': True})

@notifications_bp.route('/notifications/poll')
@login_required
def poll():
    """Returns unread, non-archived notifications created after ?since=<ISO>,
    oldest first. notifications.js calls it on each SSE ping (30s poll as
    fallback) to fire desktop alerts."""
    notif_user_id = effective_user().id

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


@notifications_bp.route('/notifications/<int:notification_id>/restore', methods=['POST'])
@login_required
def restore_notification(notification_id):

    notification = Notification.query.get_or_404(notification_id)

    # Emulation-aware ownership check, as in mark_read.
    notif_user_id = effective_user().id

    if notification.recipient_id != notif_user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    notification.is_archived = False
    db.session.commit()

    return jsonify({'success': True})

