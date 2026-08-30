"""project_overlay/flags.py — Brief Flags: create / reply / resolve / history (JSON)."""

from flask import request, abort, jsonify
from flask_login import login_required

from app.modules.core.shared.models import Project

from ._common import project_overlay_bp, _get_actor, _can_manage_flags, _can_resolve_flag

def _serialize_flag(flag, actor):
    """JSON shape for the History view — same fields as _flag_card.html so
    history and active items render identically."""
    return {
        'id': flag.id,
        'flag_type': flag.flag_type,
        'deliverable_id': flag.deliverable_id,
        'deliverable_name': flag.deliverable.name if flag.deliverable else None,
        'is_resolved': flag.is_resolved,
        'can_resolve': (not flag.is_resolved) and _can_resolve_flag(flag, actor),
        'created_by_name': flag.created_by.name if flag.created_by else 'Unknown',
        'created_at': flag.created_at.isoformat() if flag.created_at else None,
        'resolved_by_name': flag.resolved_by.name if flag.resolved_by else None,
        'resolved_at': flag.resolved_at.isoformat() if flag.resolved_at else None,
        'messages': [
            {
                'author_name': m.author.name if m.author else 'Unknown',
                'message': m.message,
                'created_at': m.created_at.isoformat() if m.created_at else None,
            }
            for m in flag.messages
        ],
    }


@project_overlay_bp.route('/projects/<int:project_id>/overlay/flags/create', methods=['POST'])
@login_required
def overlay_create_flag(project_id):
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import BriefFlag, BriefFlagMessage
    from app.modules.core.shared.services.notifications import notify_cs_of_brief_flag
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not _can_manage_flags(actor):
        return jsonify({'success': False, 'error': 'You do not have permission to raise a flag.'}), 403

    data = request.get_json(silent=True) or {}
    flag_type = data.get('flag_type')
    deliverable_id = data.get('deliverable_id')
    message_text = (data.get('message') or '').strip()
    if flag_type not in ('project', 'deliverable', 'concept', 'kv') or not message_text:
        return jsonify({'success': False, 'error': 'A message is required.'}), 400

    # A 'deliverable' flag needs a target on this project, or it renders
    # invisibly in both scopes. Guard server-side.
    if flag_type == 'deliverable':
        from app.modules.core.shared.models import Deliverable
        deliverable = Deliverable.query.get(deliverable_id) if deliverable_id else None
        if not deliverable or deliverable.project_id != project_id:
            return jsonify({'success': False, 'error': 'Pick a deliverable to flag first.'}), 400

    flag = BriefFlag(
        project_id=project_id,
        deliverable_id=deliverable_id or None,
        flag_type=flag_type,
        created_by_id=actor.id,
    )
    db.session.add(flag)
    db.session.flush()
    db.session.add(BriefFlagMessage(flag_id=flag.id, author_id=actor.id, message=message_text))
    db.session.commit()

    notify_cs_of_brief_flag(flag, project, triggered_by=actor)
    log_activity(
        'brief_flag_created', f'{actor.name} raised a {flag_type} flag on "{project.name}"',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
    )
    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/flags/<int:flag_id>/reply', methods=['POST'])
@login_required
def overlay_reply_flag(project_id, flag_id):
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import BriefFlag, BriefFlagMessage
    from app.modules.core.shared.services.notifications import notify_flag_reply
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    flag = BriefFlag.query.get_or_404(flag_id)
    if flag.project_id != project_id:
        abort(404)
    actor = _get_actor()
    if not _can_manage_flags(actor):
        return jsonify({'success': False, 'error': 'You do not have permission to reply to this flag.'}), 403

    data = request.get_json(silent=True) or {}
    message_text = (data.get('message') or '').strip()
    if not message_text:
        return jsonify({'success': False, 'error': 'A message is required.'}), 400

    db.session.add(BriefFlagMessage(flag_id=flag_id, author_id=actor.id, message=message_text))
    db.session.commit()

    notify_flag_reply(flag, project, triggered_by=actor)
    log_activity(
        'brief_flag_reply', f'{actor.name} replied to a flag on "{project.name}"',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
    )
    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/flags/<int:flag_id>/resolve', methods=['POST'])
@login_required
def overlay_resolve_flag(project_id, flag_id):
    from datetime import datetime as dt
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import BriefFlag
    from app.modules.core.shared.services.notifications import notify_cs_of_flag_resolved
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    flag = BriefFlag.query.get_or_404(flag_id)
    if flag.project_id != project_id:
        abort(404)
    actor = _get_actor()
    if not _can_resolve_flag(flag, actor):
        return jsonify({'success': False, 'error': 'Only the person who raised this flag can resolve it.'}), 403
    if flag.is_resolved:
        return jsonify({'success': False, 'error': 'This flag is already resolved.'}), 400

    flag.is_resolved = True
    flag.resolved_at = dt.utcnow()
    flag.resolved_by_id = actor.id
    db.session.commit()

    notify_cs_of_flag_resolved(flag, project, triggered_by=actor)
    log_activity(
        'brief_flag_resolved', f'{actor.name} resolved a {flag.flag_type} flag on "{project.name}"',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
    )
    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/flags/history')
@login_required
def overlay_flags_history(project_id):
    """Every flag for the requested scope, newest first. scope 'project' also
    includes concept/kv; scope 'deliverable' takes an optional customer_id so
    C&CM per-customer panels see only their own history."""
    from app.modules.core.shared.models import BriefFlag, Deliverable

    project = Project.query.get_or_404(project_id)
    scope = request.args.get('scope', 'project')

    query = BriefFlag.query.filter_by(project_id=project_id)
    if scope == 'deliverable':
        query = query.filter(BriefFlag.flag_type == 'deliverable')
        customer_id = request.args.get('customer_id', type=int)
        if customer_id:
            deliverable_ids = [
                d.id for d in Deliverable.query.filter_by(
                    project_id=project_id, project_customer_id=customer_id
                ).all()
            ]
            query = query.filter(BriefFlag.deliverable_id.in_(deliverable_ids))
    else:
        query = query.filter(BriefFlag.flag_type.in_(['project', 'concept', 'kv']))

    actor = _get_actor()
    flags = query.order_by(BriefFlag.created_at.desc()).all()
    return jsonify({'flags': [_serialize_flag(f, actor) for f in flags]})
