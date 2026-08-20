# app/routes/project_notes.py
from flask import Blueprint, render_template, request, jsonify, abort
from flask_login import login_required
from app import db
from app.models import Project, ProjectNote
from app.utils import log_activity

project_notes_bp = Blueprint('project_notes', __name__)


def _get_actor():
    # Same emulation-aware pattern used everywhere else in the overlay routes
    # (project_overlay.py, project_preproduction.py) — admins can "view as"
    # another user, and every action should attribute to whoever they're
    # emulating, not the literal logged-in admin account.
    from flask import session
    from flask_login import current_user
    from app.models import User
    emulating_id = session.get('emulating_user_id')
    return User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user


def _can_manage_notes(project, actor):
    # Same "who's actually working on this project" set used for Reference
    # Files elsewhere — CS lead, secondary CS, assigned project owner, or
    # admin/management. Broad on purpose: a note is low-stakes, unlike
    # deleting a deliverable.
    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    return (
        actor.role in ('admin', 'management')
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
        or (actor.role == 'project_owner' and actor.id == project.project_owner_id)
        or any(pd.user_id == actor.id for pd in project.assigned_designers)
    )

# becomes:
def _is_designer(user):
    return user.role in ('designer', 'team_lead')

def _overlapping_site_visit(visit_user, start_at, end_at, exclude_id=None):
    from app.models import SiteVisit
    query = SiteVisit.query.filter(
        SiteVisit.user_id == visit_user.id,
        SiteVisit.start_at < end_at,
        SiteVisit.end_at > start_at,
    )
    if exclude_id:
        query = query.filter(SiteVisit.id != exclude_id)
    return query.first()


@project_notes_bp.route('/projects/<int:project_id>/overlay/notes')
@login_required
def overlay_notes(project_id):
    from app.models import User
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    notes = ProjectNote.query.filter_by(project_id=project.id).all()
    site_visits = project.site_visits
    designers = User.query.filter(
        User.role.in_(['designer', 'team_lead'])
    ).order_by(User.name).all()

    # Merged, single-feed activity log (18 Aug 2026, per Ezekiel) — a logged
    # site visit shows up as its own row in the Notes list instead of a
    # separate read-only list under Site Visits, which becomes just the
    # logging form. Sorted by created_at (when it was actually logged),
    # not a site visit's start_at — the feed should read as "what got
    # added and when", not get reordered by a visit's own scheduled time.
    activity_items = (
        [{'type': 'note', 'sort_at': n.created_at, 'note': n} for n in notes]
        + [{'type': 'site_visit', 'sort_at': v.created_at, 'visit': v} for v in site_visits]
    )
    activity_items.sort(key=lambda item: item['sort_at'], reverse=True)

    return render_template(
        'project_overlay/_overlay_notes.html',
        project=project, activity_items=activity_items,
        can_manage_notes=_can_manage_notes(project, actor),
        can_log_site_visit=_can_log_site_visit(actor),
        designers=designers,
        actor=actor,
    )


@project_notes_bp.route('/projects/<int:project_id>/overlay/notes/create', methods=['POST'])
@login_required
def create_note(project_id):
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not _can_manage_notes(project, actor):
        abort(403)

    data = request.get_json(silent=True) or {}
    body = (data.get('body') or '').strip()
    if not body:
        return jsonify({'success': False, 'error': 'Note text is required.'}), 400

    note = ProjectNote(
        project_id=project.id, author_id=actor.id, body=body,
        file_link=(data.get('file_link') or '').strip() or None,
    )
    db.session.add(note)
    db.session.commit()

    log_activity('note_added', f'{actor.name} added a note to "{project.name}"',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True, 'note_id': note.id})

# app/routes/project_notes.py (continued)

from datetime import datetime as _dt


def _can_log_site_visit(actor):
    # management, technical designers/team leads, or project owners — per
    # Ezekiel. Admin included too, matching every other permission gate in
    # this codebase (admin is always a superset elsewhere) — flag this if
    # you actually want admin excluded, easy one-line change.
    if actor.role in ('admin', 'management', 'project_owner'):
        return True
    return actor.role in ('designer', 'team_lead') and actor.team == 'Technical'


@project_notes_bp.route('/projects/<int:project_id>/overlay/site-visits/<int:visit_id>/delete', methods=['POST'])
@login_required
def delete_site_visit(project_id, visit_id):
    from app.models import SiteVisit
    visit = SiteVisit.query.get_or_404(visit_id)
    if visit.project_id != project_id:
        abort(404)
    actor = _get_actor()
    if not (_can_log_site_visit(actor) or actor.role in ('admin', 'management')):
        abort(403)

    db.session.delete(visit)
    db.session.commit()
    return jsonify({'success': True})


@project_notes_bp.route('/projects/<int:project_id>/overlay/site-visits/create', methods=['POST'])
@login_required
def create_site_visit(project_id):
    from app.models import SiteVisit, User

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not _can_log_site_visit(actor):
        abort(403)

    data = request.get_json(silent=True) or {}

    visit_user = User.query.get(int(data['user_id'])) if data.get('user_id') else None
    if not visit_user or not _is_designer(visit_user):
        return jsonify({'success': False, 'error_type': 'invalid_designer',
                        'error': 'Please select a designer for this site visit.'}), 400

    try:
        start_at = _dt.fromisoformat(data.get('start_at'))
        end_at = _dt.fromisoformat(data.get('end_at'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error_type': 'invalid_range',
                        'error': 'Please enter a valid start and end time.'}), 400

    if end_at <= start_at:
        return jsonify({'success': False, 'error_type': 'invalid_range',
                        'error': 'Please ensure the end time is after the start time'}), 400

    conflict = _overlapping_site_visit(visit_user, start_at, end_at)
    if conflict:
        return jsonify({
            'success': False, 'error_type': 'overlap',
            'error': 'This site visit conflicts with another site visit',
            'conflict': {
                'project_name': conflict.project.name,
                'start_at': conflict.start_at.strftime('%d %b %Y, %H:%M'),
                'end_at': conflict.end_at.strftime('%d %b %Y, %H:%M'),
                'location': conflict.location,
            },
        }), 409

    visit = SiteVisit(
        project_id=project.id, user_id=visit_user.id, start_at=start_at, end_at=end_at,
        location=(data.get('location') or '').strip() or None,
        notes=(data.get('notes') or '').strip() or None,
    )
    db.session.add(visit)
    db.session.commit()

    log_activity('site_visit_logged', f'{actor.name} logged a site visit for {visit_user.name} on "{project.name}"',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True, 'visit_id': visit.id})

# app/routes/project_notes.py (continued)

@project_notes_bp.route('/projects/<int:project_id>/overlay/notes/<int:note_id>/delete', methods=['POST'])
@login_required
def delete_note(project_id, note_id):
    note = ProjectNote.query.get_or_404(note_id)
    if note.project_id != project_id:
        abort(404)
    actor = _get_actor()
    if not (note.author_id == actor.id or actor.role in ('admin', 'management')):
        abort(403)

    db.session.delete(note)
    db.session.commit()
    return jsonify({'success': True})


