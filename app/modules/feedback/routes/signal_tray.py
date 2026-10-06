"""Signal tray: compact Bug Report and Feature Request boards, plus the weekly
Friction Log.

The boards read the feedback models; writes go to the feedback routes. The
Friction Log's routes live here.
"""
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_login import login_required
from sqlalchemy.orm import joinedload

from app.modules.core.shared.extensions import db
from app.modules.core.shared.lib.capabilities import effective_user
from app.modules.core.shared.lib.org import department_label
from app.modules.core.shared.models import (
    BugReport, BugReportComment, FeatureRequest, FeatureRequestComment,
    FeatureRequestUpvote, FrictionLogEntry,
)
from app.modules.feedback.lib.friction import MAX_LENGTH, can_delete, week_start_for

signal_tray_bp = Blueprint('signal_tray', __name__)

# Stored status values and their tray labels. Keys must match the feedback
# routes' VALID_STATUSES / BUG_VALID_STATUSES.
BUG_STATUSES = [
    ('in_queue', 'In queue'),
    ('fix_in_progress', 'Fix in progress'),
    ('testing', 'Testing'),
    ('resolved', 'Resolved'),
]
FEATURE_STATUSES = [
    ('requested', 'Requested'),
    ('in_progress', 'In progress'),
    ('testing', 'Testing'),
    ('implemented', 'Implemented'),
]
SEVERITIES = [('high', 'High'), ('medium', 'Med'), ('low', 'Low')]

BUG_STATUS_LABELS = dict(BUG_STATUSES)
FEATURE_STATUS_LABELS = dict(FEATURE_STATUSES)
SEVERITY_LABELS = dict(SEVERITIES)

# Posts the Friction Log loads; older ones drop off the top.
FRICTION_HISTORY = 500


def _counts(rows, statuses):
    """Chip counts: one per status in the board's own order, plus the total."""
    tally = {key: 0 for key, _ in statuses}
    for row in rows:
        if row['status'] in tally:
            tally[row['status']] += 1
    return {
        'all': len(rows),
        'by_status': [
            {'key': key, 'label': label, 'count': tally[key]}
            for key, label in statuses
        ],
    }


def _comment_counts(model, foreign_key):
    """Comments per item in one query, so a long board stays one round trip."""
    rows = db.session.query(foreign_key, db.func.count(model.id)).group_by(foreign_key).all()
    return dict(rows)


@signal_tray_bp.route('/signal/bugs')
@login_required
def bug_board():
    counts = _comment_counts(BugReportComment, BugReportComment.bug_id)
    bugs = (BugReport.query
            .options(joinedload(BugReport.submitter))
            .order_by(BugReport.created_at.desc())
            .all())
    rows = [{
        'id': bug.id,
        'title': bug.title,
        'status': bug.status,
        'status_label': BUG_STATUS_LABELS.get(bug.status, bug.status),
        'severity': bug.severity,
        'severity_label': SEVERITY_LABELS.get(bug.severity),
        'author': bug.submitter.name if bug.submitter else '',
        'created_at': bug.created_at.isoformat() if bug.created_at else None,
        'comments': counts.get(bug.id, 0),
    } for bug in bugs]
    return jsonify({
        'rows': rows,
        'counts': _counts(rows, BUG_STATUSES),
        'severities': [{'key': k, 'label': l} for k, l in SEVERITIES],
    })


def _di_states():
    """IDs of feature requests Digital Innovation declined, via DI's intake
    service. Queued vs picked-up comes from our own status field ('requested'
    means queued); only declines are stored in DI."""
    from app.modules.digital_innovation.services.intake import declined_feature_ids

    return declined_feature_ids()


@signal_tray_bp.route('/signal/features')
@login_required
def feature_board():
    actor = effective_user()
    counts = _comment_counts(FeatureRequestComment, FeatureRequestComment.feature_id)
    votes = dict(
        db.session.query(FeatureRequestUpvote.feature_id, db.func.count(FeatureRequestUpvote.id))
        .group_by(FeatureRequestUpvote.feature_id).all()
    )
    mine = {
        row.feature_id for row in
        FeatureRequestUpvote.query.filter_by(user_id=actor.id).all()
    }
    declined = _di_states()

    features = (FeatureRequest.query
                .options(joinedload(FeatureRequest.submitter))
                .order_by(FeatureRequest.created_at.desc())
                .all())
    rows = []
    for feature in features:
        if feature.id in declined:
            di_state = 'declined'
        elif feature.status == 'requested':
            di_state = 'queued'
        else:
            di_state = 'picked_up'
        rows.append({
            'id': feature.id,
            'title': feature.title,
            'status': feature.status,
            'status_label': FEATURE_STATUS_LABELS.get(feature.status, feature.status),
            'author': feature.submitter.name if feature.submitter else '',
            'created_at': feature.created_at.isoformat() if feature.created_at else None,
            'comments': counts.get(feature.id, 0),
            'upvotes': votes.get(feature.id, 0),
            'voted': feature.id in mine,
            'di_state': di_state,
        })

    # Most-upvoted first.
    rows.sort(key=lambda r: r['upvotes'], reverse=True)
    return jsonify({'rows': rows, 'counts': _counts(rows, FEATURE_STATUSES)})


@signal_tray_bp.route('/signal/friction')
@login_required
def friction_log():
    """The latest Friction Log posts, oldest first, grouped by week."""
    actor = effective_user()
    entries = (FrictionLogEntry.query
               .options(joinedload(FrictionLogEntry.author))
               .order_by(FrictionLogEntry.week_start.desc(),
                         FrictionLogEntry.created_at.desc(),
                         FrictionLogEntry.id.desc())
               .limit(FRICTION_HISTORY)
               .all())
    entries.reverse()

    weeks = []
    for entry in entries:
        key = entry.week_start.isoformat()
        if not weeks or weeks[-1]['week_start'] != key:
            weeks.append({'week_start': key, 'entries': []})
        weeks[-1]['entries'].append({
            'id': entry.id,
            'body': entry.body,
            'author': entry.author.name if entry.author else '',
            'department': department_label(entry.author),
            'created_at': entry.created_at.isoformat() if entry.created_at else None,
            'can_delete': can_delete(entry, actor),
        })

    return jsonify({
        'weeks': weeks,
        'current_week': week_start_for().isoformat(),
        'max_length': MAX_LENGTH,
    })


@signal_tray_bp.route('/signal/friction', methods=['POST'])
@login_required
def post_friction():
    """Anyone signed in may post. While an admin emulates, the post is the
    emulated person's, as in the chat tray."""
    actor = effective_user()
    body = ((request.get_json() or {}).get('body') or '').strip()
    if not body:
        return jsonify({'success': False, 'error': 'Write something first'}), 400
    if len(body) > MAX_LENGTH:
        return jsonify({'success': False,
                        'error': f'Keep it under {MAX_LENGTH} characters'}), 400

    db.session.add(FrictionLogEntry(author_id=actor.id, body=body, week_start=week_start_for()))
    db.session.commit()
    return jsonify({'success': True})


@signal_tray_bp.route('/signal/friction/<int:entry_id>', methods=['DELETE'])
@login_required
def delete_friction(entry_id):
    """Delete a post: the author's own, or any post for an admin."""
    actor = effective_user()
    entry = FrictionLogEntry.query.get(entry_id)
    if entry is None:
        return jsonify({'success': False, 'error': 'Post not found'}), 404
    if not can_delete(entry, actor):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    db.session.delete(entry)
    db.session.commit()
    return jsonify({'success': True})


def _unread_since(seen_at):
    """Count of new bugs, features and friction entries since the user last
    opened the tray, for the launcher bubble."""
    if seen_at is None:
        # Never opened it: the bubble would be the whole history, which is noise.
        return 0
    return (
        BugReport.query.filter(BugReport.created_at > seen_at).count()
        + FeatureRequest.query.filter(FeatureRequest.created_at > seen_at).count()
        + FrictionLogEntry.query.filter(FrictionLogEntry.created_at > seen_at).count()
    )


@signal_tray_bp.route('/signal/unread')
@login_required
def unread():
    actor = effective_user()
    return jsonify({'unread': _unread_since(actor.signal_seen_at)})


@signal_tray_bp.route('/signal/seen', methods=['POST'])
@login_required
def mark_seen():
    """Opening the tray clears its bubble."""
    actor = effective_user()
    actor.signal_seen_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True})
