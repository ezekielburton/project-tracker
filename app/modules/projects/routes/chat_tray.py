"""Chat tray: the global list of project conversations.

The thread pane reuses the overlay's chat drawer (project_notes.render_project_chat,
driven by ProjectChatPanel in JS).
"""
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_login import login_required
from sqlalchemy.orm import joinedload

from app.modules.core.shared.extensions import db
from app.modules.core.shared.lib.capabilities import can, effective_user
from app.modules.core.shared.models import (
    ChatTrayProject, Project, ProjectActivitySeen, ProjectDesigner,
    ProjectNote, ProjectSecondaryCS,
)

chat_tray_bp = Blueprint('chat_tray', __name__)

# Max rows returned; the list is newest-first, so the cut drops the stalest.
_LIST_CAP = 50


def _unread_baseline():
    """Chat older than this cutoff never counts as unread. Shared with the
    Projects table's chat dot so the two always agree."""
    from app.modules.core.shared.lib.utils import ACTIVITY_SEEN_ROLLOUT_CUTOFF
    return ACTIVITY_SEEN_ROLLOUT_CUTOFF


def _pool_query(user):
    """Non-draft projects the user is on: CS lead, secondary CS, owner, or
    assigned designer. Keep in step with project_notes._can_manage_notes."""
    secondary_ids = db.session.query(ProjectSecondaryCS.project_id).filter_by(user_id=user.id).subquery()
    assigned_ids = db.session.query(ProjectDesigner.project_id).filter_by(user_id=user.id).subquery()
    return Project.query.filter(
        db.or_(
            Project.cs_lead_id == user.id,
            Project.project_owner_id == user.id,
            Project.id.in_(secondary_ids),
            Project.id.in_(assigned_ids),
        ),
        Project.project_status != 'draft',
    )


def _reachable_query(user):
    """Projects the user may open or add. manage_projects reaches every
    non-draft project; everyone else gets their pool."""
    if can('manage_projects', user):
        return Project.query.filter(Project.project_status != 'draft')
    return _pool_query(user)


def _tray_state(user):
    """This user's tray rows, keyed by project."""
    return {r.project_id: r for r in ChatTrayProject.query.filter_by(user_id=user.id).all()}


def _tray_row(user, project_id):
    """Get or create the tray row for user + project. Caller commits."""
    row = ChatTrayProject.query.filter_by(user_id=user.id, project_id=project_id).first()
    if not row:
        row = ChatTrayProject(user_id=user.id, project_id=project_id)
        db.session.add(row)
    return row


def _initials(name):
    parts = [p for p in (name or '').split() if p]
    return ''.join(p[0] for p in parts[:2]).upper() or '?'


def _last_notes(project_ids):
    """Newest message per project, in one query (not one per project).
    Ties on created_at keep the first row seen."""
    if not project_ids:
        return {}
    latest = (
        db.session.query(
            ProjectNote.project_id.label('project_id'),
            db.func.max(ProjectNote.created_at).label('at'),
        )
        .filter(ProjectNote.project_id.in_(project_ids))
        .group_by(ProjectNote.project_id)
        .subquery()
    )
    rows = (
        ProjectNote.query
        .join(latest, db.and_(
            ProjectNote.project_id == latest.c.project_id,
            ProjectNote.created_at == latest.c.at,
        ))
        .options(joinedload(ProjectNote.author))
        .all()
    )
    by_project = {}
    for note in rows:
        by_project.setdefault(note.project_id, note)
    return by_project


def _unread_counts(project_ids, user):
    """Per project, count others' messages newer than the user's chat watermark.
    Projects with no watermark row fall back to the unread baseline."""
    if not project_ids:
        return {}
    seen = (
        db.session.query(
            ProjectActivitySeen.project_id.label('project_id'),
            ProjectActivitySeen.last_seen_chat_at.label('seen_at'),
        )
        .filter(ProjectActivitySeen.user_id == user.id)
        .subquery()
    )
    rows = (
        db.session.query(ProjectNote.project_id, db.func.count(ProjectNote.id))
        .outerjoin(seen, seen.c.project_id == ProjectNote.project_id)
        .filter(
            ProjectNote.project_id.in_(project_ids),
            ProjectNote.author_id != user.id,
            ProjectNote.created_at > db.func.coalesce(seen.c.seen_at, _unread_baseline()),
        )
        .group_by(ProjectNote.project_id)
        .all()
    )
    return dict(rows)


@chat_tray_bp.route('/chat-tray/conversations')
@login_required
def conversations():
    """Left pane: pool projects with chat, plus added or pinned ones, minus
    hidden ones with no newer message. Pinned first, then newest activity."""
    actor = effective_user()
    state = _tray_state(actor)

    projects = _pool_query(actor).all()
    # Added or pinned projects can sit outside your own pool.
    kept = {pid for pid, row in state.items() if row.added_at or row.pinned_at}
    off_pool = kept - {p.id for p in projects}
    if off_pool:
        projects = projects + Project.query.filter(Project.id.in_(off_pool)).all()
    project_ids = [p.id for p in projects]

    last_notes = _last_notes(project_ids)
    unread = _unread_counts(project_ids, actor)

    rows = []
    for project in projects:
        row = state.get(project.id)
        note = last_notes.get(project.id)
        added = bool(row and row.added_at)
        pinned = bool(row and row.pinned_at)

        # Hidden until a newer message arrives; a pin overrides a hide.
        if row and row.hidden_at and not pinned:
            if note is None or note.created_at is None or note.created_at <= row.hidden_at:
                continue

        if note is None and not added and not pinned:
            continue

        rows.append({
            'project_id': project.id,
            'name': project.name,
            'job_number': project.job_number,
            'initials': _initials(project.name),
            'added': added,
            'pinned': pinned,
            'unread': unread.get(project.id, 0),
            'last_message': None if note is None else {
                'author': note.author.name if note.author else '',
                'text': note.display_text(),
                'at': note.created_at.isoformat() if note.created_at else None,
            },
        })

    # Two stable sorts: newest first, then pinned to the top keeping that order.
    rows.sort(key=lambda r: (r['last_message'] or {}).get('at') or '', reverse=True)
    rows.sort(key=lambda r: 0 if r['pinned'] else 1)

    return jsonify({
        'conversations': rows[:_LIST_CAP],
        'unread_total': sum(r['unread'] for r in rows),
    })


@chat_tray_bp.route('/chat-tray/addable')
@login_required
def addable_projects():
    """The ＋ picker: every project the user could add, by name."""
    actor = effective_user()
    projects = _reachable_query(actor).order_by(Project.name).all()
    return jsonify({'projects': [
        {'project_id': p.id, 'name': p.name, 'job_number': p.job_number}
        for p in projects
    ]})


@chat_tray_bp.route('/chat-tray/projects', methods=['POST'])
@login_required
def add_project():
    """Add a conversation to the tray and clear any hide."""
    actor = effective_user()
    project_id = (request.get_json() or {}).get('project_id')
    project = _reachable_query(actor).filter(Project.id == project_id).first() if project_id else None
    if not project:
        return jsonify({'success': False, 'error': 'Not one of your projects'}), 403

    row = _tray_row(actor, project.id)
    row.added_at = datetime.utcnow()
    row.hidden_at = None
    db.session.commit()
    return jsonify({'success': True})


@chat_tray_bp.route('/chat-tray/projects/<int:project_id>', methods=['DELETE'])
@login_required
def hide_project(project_id):
    """Hide a conversation until someone posts in it again. Clears add and pin."""
    actor = effective_user()
    project = _reachable_query(actor).filter(Project.id == project_id).first()
    if not project:
        return jsonify({'success': False, 'error': 'Not one of your projects'}), 403

    row = _tray_row(actor, project.id)
    row.hidden_at = datetime.utcnow()
    row.added_at = None
    row.pinned_at = None
    db.session.commit()
    return jsonify({'success': True})


@chat_tray_bp.route('/chat-tray/projects/<int:project_id>/pin', methods=['POST'])
@login_required
def pin_project(project_id):
    """Pin or unpin a conversation. Pinning clears any hide."""
    actor = effective_user()
    project = _reachable_query(actor).filter(Project.id == project_id).first()
    if not project:
        return jsonify({'success': False, 'error': 'Not one of your projects'}), 403

    pinned = bool((request.get_json() or {}).get('pinned', True))
    row = _tray_row(actor, project.id)
    row.pinned_at = datetime.utcnow() if pinned else None
    if pinned:
        row.hidden_at = None
    db.session.commit()
    return jsonify({'success': True, 'pinned': pinned})


@chat_tray_bp.route('/chat-tray/projects/<int:project_id>/thread')
@login_required
def project_thread(project_id):
    """Right pane: the overlay's chat drawer, gated to reachable projects.
    Rendering it advances the chat watermark, clearing this project's unread."""
    from app.modules.projects.routes.project_notes import render_project_chat

    actor = effective_user()
    project = _reachable_query(actor).filter(Project.id == project_id).first()
    if not project:
        return jsonify({'error': 'Not one of your projects'}), 403
    return render_project_chat(project, actor)
