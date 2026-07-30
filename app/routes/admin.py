import os
import uuid
from functools import wraps
from datetime import timezone, timedelta
from flask import Blueprint, jsonify, session, url_for, request
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import (
    User, Client, Customer, Project, ProjectFile,
    DeliverableType, DeliverableTypeDiscipline,
    DesignType, DesignDirection, ActivityLog, NotificationSound
)
from app.utils import log_activity
from app.notifications import broadcast_update_email
from werkzeug.security import generate_password_hash

DUBAI_TZ = timezone(timedelta(hours=4))

admin_bp = Blueprint('admin', __name__)

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            return jsonify({'success': False, 'error': 'Forbidden'}), 403
        return f(*args, **kwargs)
    return decorated

@admin_bp.route('/admin/api/users', methods=['GET'])
@login_required
@admin_required
def list_users():
    users = User.query.order_by(User.name).all()
    return jsonify([{'id': u.id, 'name': u.name, 'email': u.email, 'role': u.role, 'team': u.team} for u in users])

@admin_bp.route ('/admin/emulate/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def start_emulation(user_id):
    user = User.query.get_or_404(user_id)
    if user.role == 'admin':
     return jsonify({'success': False, 'error': 'Cannot emulate an admin account'}), 400
    session['emulating_user_id'] = user.id
    return jsonify({'success': True, 'redirect_url': url_for('main.index')})

@admin_bp.route('/admin/emulate/exit', methods=['POST'])
@login_required
def exit_emulation():
    session.pop('emulating_user_id', None)
    return jsonify({'success': True, 'redirect_url': url_for('main.index')})

@admin_bp.route('/admin/api/users', methods=['POST'])
@login_required
@admin_required
def create_user():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip()
    password = (data.get('password') or '').strip()
    role = (data.get('role') or '').strip()
    team = (data.get('team') or '').strip() or None

    if not all([name, email, password, role]):
        return jsonify({'success': False, 'error': 'All fields are required'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'error': 'Email already exists'}), 400

    if role not in ['designer', 'team_lead']:
        team = None

    user = User(
        name=name,
        email=email,
        password_hash=generate_password_hash(password),
        role=role,
        team=team
    )
    db.session.add(user)
    db.session.commit()
    log_activity('user_created', f'User "{user.name}" created with role {role}', user=current_user, entity_type='user', entity_name=user.name, entity_id=user.id)
    return jsonify({'success': True, 'user': {'id': user.id, 'name': user.name, 'role': user.role, 'team': user.team}})

SOUND_UPLOAD_FOLDER = os.path.join('app', 'static', 'sounds')
ALLOWED_SOUND_EXTENSIONS = {'mp3', 'wav', 'ogg', 'm4a', 'aac'}

@admin_bp.route('/admin/api/sounds', methods=['GET'])
@login_required
@admin_required
def list_sounds():
    """List all admin-uploaded notification sounds, newest first."""
    sounds = NotificationSound.query.order_by(NotificationSound.created_at.desc()).all()
    return jsonify([{
        'id': s.id,
        'name': s.name,
        'url': url_for('static', filename=f'sounds/{s.filename}'),
        'uploaded_by': s.uploaded_by.name if s.uploaded_by else None,
    } for s in sounds])

@admin_bp.route('/admin/api/sounds', methods=['POST'])
@login_required
@admin_required
def upload_sound():
    """Upload a new notification sound file. Admin only."""
    name = (request.form.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Please provide a name for this sound'}), 400

    if 'file' not in request.files or request.files['file'].filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    file = request.files['file']
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_SOUND_EXTENSIONS:
        return jsonify({'success': False, 'error': f'File type .{ext} not allowed'}), 400

    # Prefix with a short uuid so two admins uploading "chime.mp3" never collide
    # or silently overwrite each other's file.
    stored_filename = f'{uuid.uuid4().hex[:8]}_{secure_filename(file.filename)}'
    os.makedirs(SOUND_UPLOAD_FOLDER, exist_ok=True)
    file.save(os.path.join(SOUND_UPLOAD_FOLDER, stored_filename))

    sound = NotificationSound(name=name, filename=stored_filename, uploaded_by_id=current_user.id)
    db.session.add(sound)
    db.session.commit()

    log_activity('notification_sound_added', f'{current_user.name} added notification sound "{name}"',
                 user=current_user, entity_type='notification_sound', entity_name=name, entity_id=sound.id)
    return jsonify({'success': True, 'sound': {'id': sound.id, 'name': sound.name,
                    'url': url_for('static', filename=f'sounds/{stored_filename}')}})


@admin_bp.route('/admin/api/sounds/<int:sound_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_sound(sound_id):
    """Delete a notification sound — removes the DB row and the file on disk."""
    sound = NotificationSound.query.get_or_404(sound_id)
    name = sound.name  # capture before delete — attributes clear post-commit

    file_path = os.path.join(SOUND_UPLOAD_FOLDER, sound.filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    db.session.delete(sound)
    db.session.commit()

    log_activity('notification_sound_removed', f'{current_user.name} removed notification sound "{name}"',
                 user=current_user, entity_type='notification_sound', entity_name=name, entity_id=sound_id)
    return jsonify({'success': True})

@admin_bp.route('/admin/api/users/<int:user_id>', methods=['PATCH'])
@login_required
@admin_required
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json()

    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip()
    role = (data.get('role') or '').strip()
    team = (data.get('team') or '').strip() or None
    password = (data.get('password') or '').strip()

    if not name or not email or not role:
        return jsonify({'success': False, 'error': 'Name, email and role are required'}), 400

    existing = User.query.filter_by(email=email).first()
    if existing and existing.id != user_id:
        return jsonify({'success': False, 'error': 'That email is already in use'}), 400

    if role not in ['designer', 'team_lead']:
        team = None

    user.name = name
    user.email = email
    user.role = role
    user.team = team

    if password:
        user.set_password(password)

    db.session.commit()
    return jsonify({'success': True, 'user': {'id': user.id, 'name': user.name, 'email': user.email, 'role': user.role, 'team': user.team}})


@admin_bp.route('/admin/api/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def admin_reset_password(user_id):
    user = User.query.get_or_404(user_id)
    user.set_password('Vitamin2026!')
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/admin/api/users/<int:user_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_user(user_id):
    from sqlalchemy.exc import IntegrityError

    if user_id == current_user.id:
        return jsonify({'success': False, 'error': 'Cannot delete your own account'}), 400

    user = User.query.get_or_404(user_id)

    # Hard blocks — these columns are NOT NULL so we can't null them out.
    # The admin must reassign/delete those records manually first.
    cs_lead_count = Project.query.filter_by(cs_lead_id=user_id).count()
    if cs_lead_count:
        return jsonify({'success': False,
                        'error': f'This user is the CS Lead on {cs_lead_count} project(s). '
                                 f'Reassign those projects to another CS before deleting.'}), 400

    created_count = Project.query.filter_by(created_by_id=user_id).count()
    if created_count:
        return jsonify({'success': False,
                        'error': f'This user created {created_count} project(s). '
                                 f'Delete or reassign those projects before deleting the account.'}), 400

    uid = user_id
    try:
        t = db.text

        # ── Delete rows owned solely by this user ─────────────────────────────
        db.session.execute(t('DELETE FROM notifications WHERE recipient_id = :u'), {'u': uid})
        db.session.execute(t('DELETE FROM project_secondary_cs WHERE user_id = :u'), {'u': uid})
        db.session.execute(t('DELETE FROM project_secondary_cs_regions WHERE user_id = :u'), {'u': uid})
        db.session.execute(t('DELETE FROM project_designers WHERE user_id = :u'), {'u': uid})
        db.session.execute(t('DELETE FROM project_reviewers WHERE user_id = :u'), {'u': uid})
        db.session.execute(t('DELETE FROM project_approvals WHERE reviewer_id = :u'), {'u': uid})
        db.session.execute(t('DELETE FROM deliverable_assignments WHERE designer_id = :u'), {'u': uid})
        db.session.execute(t('DELETE FROM feature_request_upvotes WHERE user_id = :u'), {'u': uid})
        db.session.execute(t('DELETE FROM feature_request_comments WHERE user_id = :u'), {'u': uid})
        db.session.execute(t('DELETE FROM blog_comments WHERE user_id = :u'), {'u': uid})
        db.session.execute(t('DELETE FROM bug_report_comments WHERE user_id = :u'), {'u': uid})
        db.session.execute(t('DELETE FROM sidebar_clicks WHERE user_id = :u'), {'u': uid})

        # ── Null out nullable FK references ───────────────────────────────────
        db.session.execute(t('UPDATE notifications SET triggered_by_id = NULL WHERE triggered_by_id = :u'), {'u': uid})
        db.session.execute(t('UPDATE project_secondary_cs SET added_by_id = NULL WHERE added_by_id = :u'), {'u': uid})
        db.session.execute(t('UPDATE projects SET concept_designer_id = NULL WHERE concept_designer_id = :u'), {'u': uid})
        db.session.execute(t('UPDATE projects SET kv_designer_id = NULL WHERE kv_designer_id = :u'), {'u': uid})
        db.session.execute(t('UPDATE projects SET lead_designer_id = NULL WHERE lead_designer_id = :u'), {'u': uid})
        db.session.execute(t('UPDATE projects SET approved_by_id = NULL WHERE approved_by_id = :u'), {'u': uid})
        db.session.execute(t('UPDATE project_submissions SET flagged_by_id = NULL WHERE flagged_by_id = :u'), {'u': uid})
        db.session.execute(t('UPDATE project_submissions SET submitted_by_id = NULL WHERE submitted_by_id = :u'), {'u': uid})
        db.session.execute(t('UPDATE project_posm_channels SET approved_by_id = NULL WHERE approved_by_id = :u'), {'u': uid})
        db.session.execute(t('UPDATE brief_flags SET resolved_by_id = NULL WHERE resolved_by_id = :u'), {'u': uid})
        db.session.execute(t('UPDATE activity_logs SET user_id = NULL WHERE user_id = :u'), {'u': uid})

        db.session.delete(user)
        db.session.commit()
        return jsonify({'success': True})

    except IntegrityError as exc:
        db.session.rollback()
        # Surface which table is still holding a reference
        msg = str(exc.orig) if hasattr(exc, 'orig') else str(exc)
        table = 'unknown table'
        for t_name in ['project_files', 'project_submissions', 'project_revisions',
                        'brief_flags', 'brief_flag_messages', 'blog_posts',
                        'feature_requests', 'bug_reports', 'deliverable_assignments',
                        'clients']:
            if t_name in msg:
                table = t_name.replace('_', ' ')
                break
        return jsonify({'success': False,
                        'error': f'Could not delete — this user still has records in {table} '
                                 f'that must be removed first.'}), 400

# ── Project Tools ────────────────────────────────────────────────────────────

@admin_bp.route('/admin/api/clients', methods=['GET'])
@login_required
@admin_required
def list_clients():
    clients = Client.query.order_by(Client.name).all()
    return jsonify([{'id': c.id, 'name': c.name} for c in clients])

@admin_bp.route('/admin/api/clients', methods=['POST'])
@login_required
@admin_required
def create_client():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400
    if Client.query.filter_by(name=name).first():
        return jsonify({'success': False, 'error': 'Client already exists'}), 400
    client = Client(name=name, created_by=current_user)
    db.session.add(client)
    db.session.commit()
    log_activity('client_created', f'Client "{client.name}" added', user=current_user, entity_type='client', entity_name=client.name, entity_id=client.id)
    return jsonify({'success': True, 'client': {'id': client.id, 'name': client.name}})

@admin_bp.route('/admin/api/clients/<int:client_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_client(client_id):
    client = Client.query.get_or_404(client_id)
    name = client.name
    db.session.delete(client)
    db.session.commit()
    log_activity('client_deleted', f'Client "{name}" deleted', user=current_user, entity_type='client', entity_name=name)
    return jsonify({'success': True})

@admin_bp.route('/admin/api/customers', methods=['GET'])
@login_required
@admin_required
def list_customers():
    customers = Customer.query.order_by(Customer.region, Customer.name).all()
    return jsonify([{'id': c.id, 'name': c.name, 'region': c.region} for c in customers])

@admin_bp.route('/admin/api/customers', methods=['POST'])
@login_required
@admin_required
def create_customer():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    region = (data.get('region') or '').strip().lower()
    if not name or not region:
        return jsonify({'success': False, 'error': 'Name and region are required'}), 400
    customer = Customer(name=name, region=region)
    db.session.add(customer)
    db.session.commit()
    log_activity('customer_created', f'Customer "{customer.name}" ({customer.region}) added', user=current_user, entity_type='customer', entity_name=customer.name, entity_id=customer.id)
    return jsonify({'success': True, 'customer': {'id': customer.id, 'name': customer.name, 'region': customer.region}})

@admin_bp.route('/admin/api/customers/<int:customer_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    name = customer.name
    db.session.delete(customer)
    db.session.commit()
    log_activity('customer_deleted', f'Customer "{name}" deleted', user=current_user, entity_type='customer', entity_name=name)
    return jsonify({'success': True})

@admin_bp.route('/admin/api/projects', methods=['GET'])
@login_required
@admin_required
def list_projects():
    projects = Project.query.filter(Project.project_status != 'draft').order_by(Project.name).all()
    return jsonify([{'id': p.id, 'name': p.name, 'job_number': p.job_number, 'cs_lead': p.cs_lead.name if p.cs_lead else '—', 'status': p.project_status} for p in projects])

@admin_bp.route('/admin/api/projects/<int:project_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_project(project_id):
    import os
    from flask import current_app

    project = Project.query.get_or_404(project_id)
    name = project.name

    # Remove uploaded reference files from disk — cascade handles the DB rows
    upload_folder = current_app.config['UPLOAD_FOLDER']
    for ref_file in project.reference_files:
        file_path = os.path.join(upload_folder, ref_file.filename)
        if os.path.exists(file_path):
            os.remove(file_path)

    db.session.delete(project)
    db.session.commit()
    log_activity('project_deleted', f'Project "{name}" deleted', user=current_user, entity_type='project', entity_name=name)
    return jsonify({'success': True})

@admin_bp.route('/admin/api/drafts', methods=['GET'])
@login_required
@admin_required
def list_drafts():
    # Include job_number so the admin drafts panel can display and distinguish them.
    drafts = Project.query.filter_by(project_status='draft').order_by(Project.name).all()
    return jsonify([{
        'id': d.id,
        'name': d.name,
        'job_number': d.job_number or '',
        'cs_lead': d.cs_lead.name if d.cs_lead else '—'
    } for d in drafts])

@admin_bp.route('/admin/api/drafts/<int:draft_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_draft_admin(draft_id):
    draft = Project.query.get_or_404(draft_id)
    name = draft.name
    # Deleting the project row also removes the job_number (UNIQUE column lives on
    # the same row), so no separate step is needed to free the number.
    db.session.delete(draft)
    db.session.commit()
    log_activity('draft_deleted', f'Draft "{name}" deleted', user=current_user, entity_type='project', entity_name=name)
    return jsonify({'success': True})


# ── Job Numbers ────────────────────────────────────────────────────────────────
# Admin can see every project that has a job number assigned and clear individual
# numbers (set to NULL) without deleting the project itself.  Useful when a
# draft was abandoned without being deleted, leaving its number reserved.

@admin_bp.route('/admin/api/job-numbers', methods=['GET'])
@login_required
@admin_required
def list_job_numbers():
    """Return every project that has a job_number set, sorted by number."""
    projects = (
        Project.query
        .filter(Project.job_number != None)  # noqa: E711 — SQLAlchemy IS NOT NULL
        .order_by(Project.job_number)
        .all()
    )
    return jsonify([{
        'id':         p.id,
        'name':       p.name,
        'job_number': p.job_number,
        'status':     p.project_status,
        'cs_lead':    p.cs_lead.name if p.cs_lead else '—',
    } for p in projects])


@admin_bp.route('/admin/api/job-numbers/<int:project_id>', methods=['DELETE'])
@login_required
@admin_required
def clear_job_number(project_id):
    """Clear (set to NULL) the job_number field on a project.
    The project itself is NOT deleted — only the number is freed so it can be
    reassigned.  Use the Projects or Drafts tab to delete the project itself.
    """
    project = Project.query.get_or_404(project_id)
    old_number = project.job_number
    if not old_number:
        return jsonify({'success': False, 'error': 'This project has no job number.'}), 400
    project.job_number = None
    db.session.commit()
    log_activity(
        'job_number_cleared',
        f'Job number "{old_number}" cleared from "{project.name}"',
        user=current_user,
        entity_type='project',
        entity_name=project.name,
        entity_id=project.id
    )
    return jsonify({'success': True})

@admin_bp.route('/admin/api/deliverable-types', methods=['GET'])
@login_required
@admin_required
def list_deliverable_types():
    types = DeliverableType.query.order_by(DeliverableType.name).all()
    return jsonify([{
        'id': dt.id,
        'name': dt.name,
        'client': dt.client.name if dt.client else '—',
        'customer': dt.customer.name if dt.customer else '—',
        'region': dt.customer.region if dt.customer else '—',
        'disciplines': [d.team for d in dt.disciplines],
        'is_custom': dt.is_custom,
        'reference_image': dt.reference_image,
        'template_filename': dt.template_filename
    } for dt in types])
    

@admin_bp.route('/admin/api/deliverable-types/<int:type_id>', methods=['PATCH'])
@login_required
@admin_required
def update_deliverable_type(type_id):
    dt = DeliverableType.query.get_or_404(type_id)
    data = request.get_json()
    name = (data.get('name') or '').strip()
    disciplines = data.get('disciplines', [])
    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400
    dt.name = name
    # Only touch reference_image if the key was actually sent. Without this
    # check, saving a plain name/discipline edit (no new image chosen) would
    # send reference_image as absent/None and silently wipe out whatever
    # image was already set — the admin isn't re-uploading one every time
    # they save, so "not present" has to mean "leave it alone."
    if 'reference_image' in data:
        dt.reference_image = data['reference_image'] # a filename, or None to explicitly clear it  
    if 'template_filename' in data:
        dt.template_filename = data['template_filename']  
    DeliverableTypeDiscipline.query.filter_by(deliverable_type_id=dt.id).delete()
    for team in disciplines:
        db.session.add(DeliverableTypeDiscipline(deliverable_type_id=dt.id, team=team))
    db.session.commit()
    log_activity('deliverable_updated', f'Deliverable type "{dt.name}" updated', user=current_user, entity_type='deliverable', entity_name=dt.name, entity_id=dt.id)
    return jsonify({'success': True, 'type': {'id': dt.id, 'name': dt.name, 'disciplines': disciplines, 'reference_image': dt.reference_image, 'template_filename': dt.template_filename}})

@admin_bp.route('/admin/api/deliverable-types/upload-template', methods=['POST'])
@login_required
@admin_required
def upload_deliverable_type_template():
    """
    Uploads a template file (.ai) for a deliverable type. Same two-step
    pattern as upload_deliverable_type_image() in projects_brief.py:
    upload first, get back a filename, then include that filename in the
    create/update payload below. Stored on local disk (app/file_templates/),
    not the NAS — these are small per-store template files.
    """
    import os, uuid
    from app.routes.file_templates import TEMPLATE_UPLOAD_FOLDER

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ('ai', 'zip'):
        return jsonify({'success': False, 'error': 'Only .ai files are supported'}), 400

    stored_filename = f'{uuid.uuid4().hex[:8]}.{ext}'
    os.makedirs(TEMPLATE_UPLOAD_FOLDER, exist_ok=True)
    file.save(os.path.join(TEMPLATE_UPLOAD_FOLDER, stored_filename))

    return jsonify({'success': True, 'filename': stored_filename})

@admin_bp.route('/admin/api/deliverable-types', methods=['POST'])
@login_required
@admin_required
def create_deliverable_type():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    client_id = data.get('client_id')
    customer_id = data.get('customer_id')
    disciplines = data.get('disciplines', [])
    is_custom = bool(data.get('is_custom', False))
    reference_image = data.get('reference_image')
    template_filename = data.get('template_filename')
    if not name or not client_id or not customer_id:
        return jsonify({'success': False, 'error': 'Name, client, and customer are required'}), 400
    dt = DeliverableType(
        name=name,
        client_id=int(client_id),
        customer_id=int(customer_id),
        is_custom=is_custom,
        reference_image=reference_image,
        template_filename=template_filename
    )
    db.session.add(dt)
    db.session.flush()
    for team in disciplines:
        db.session.add(DeliverableTypeDiscipline(deliverable_type_id=dt.id, team=team))
    db.session.commit()
    log_activity('deliverable_created', f'Deliverable type "{dt.name}" created', user=current_user, entity_type='deliverable', entity_name=dt.name, entity_id=dt.id)
    return jsonify({'success': True, 'type': {
        'id': dt.id,
        'name': dt.name,
        'client': dt.client.name,
        'customer': dt.customer.name,
        'region': dt.customer.region,
        'disciplines': disciplines,
        'is_custom': dt.is_custom,
        'reference_image': dt.reference_image,
        'template_filename': dt.template_filename
    }})

@admin_bp.route('/admin/api/deliverable-types/<int:type_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_deliverable_type(type_id):
    dt = DeliverableType.query.get_or_404(type_id)
    name = dt.name
    db.session.delete(dt)
    db.session.commit()
    log_activity('deliverable_deleted', f'Deliverable type "{name}" deleted', user=current_user, entity_type='deliverable', entity_name=name)
    return jsonify({'success': True})

# Activity Log
@admin_bp.route('/admin/api/activity', methods=['GET'])
@login_required
@admin_required
def list_activity():
    from datetime import datetime
    query = ActivityLog.query

    search = request.args.get('search', '').strip()
    from_date = request.args.get('from', '').strip()
    to_date = request.args.get('to', '').strip()
    category = request.args.get('category', '').strip()  # Creation / Flags / Deletions / Assignments / Edits / Other

    # Category → action keyword mapping.
    # Each category maps to a list of action strings that belong to it.
    # "Other" is a special sentinel handled below — it matches anything NOT
    # in any of the other categories.
    CATEGORY_KEYWORDS = {
        'creation':    ['created', 'uploaded', 'added', 'internal_review_submitted', 'submission_uploaded'],
        'flags':       ['flagged', 'submission_flagged'],
        'deletions':   ['deleted'],
        'assignments': ['assigned'],
        'edits':       ['updated', 'changed', 'status_changed', 'deliverable_status_changed',
                        'submitted_to_client', 'internal_review_submitted'],
    }
    # Collect every keyword that belongs to a named category (used to invert for "Other")
    ALL_NAMED_KEYWORDS = [kw for kws in CATEGORY_KEYWORDS.values() for kw in kws]

    if search:
        pattern = f'%{search}%'
        query = query.filter(
            db.or_(
                ActivityLog.description.ilike(pattern),
                ActivityLog.entity_name.ilike(pattern)
            )
        )
    if from_date:
        from_dt_utc = datetime.fromisoformat(from_date) - timedelta(hours=4)
        query = query.filter(ActivityLog.created_at >= from_dt_utc)
    if to_date:
        to_dt_utc = datetime.fromisoformat(to_date + ' 23:59:59') - timedelta(hours=4)
        query = query.filter(ActivityLog.created_at <= to_dt_utc)

    if category and category != 'all':
        cat_lower = category.lower()
        if cat_lower == 'other':
            # "Other" = actions that don't match any keyword in any named category
            query = query.filter(
                ~db.or_(*[ActivityLog.action.ilike(f'%{kw}%') for kw in ALL_NAMED_KEYWORDS])
            )
        elif cat_lower in CATEGORY_KEYWORDS:
            keywords = CATEGORY_KEYWORDS[cat_lower]
            query = query.filter(
                db.or_(*[ActivityLog.action.ilike(f'%{kw}%') for kw in keywords])
            )

    entries = query.order_by(ActivityLog.created_at.desc()).limit(500).all()
    return jsonify([{
        'id': e.id,
        'action': e.action,
        'description': e.description,
        'entity_type': e.entity_type,
        'entity_name': e.entity_name,
        'entity_id': e.entity_id,
        'user': e.user.name if e.user else 'System',
        'created_at': e.created_at.replace(tzinfo=timezone.utc).astimezone(DUBAI_TZ).strftime('%d %b %Y, %H:%M')
    } for e in entries])

@admin_bp.route('/admin/api/activity/export', methods=['POST'])
@login_required
@admin_required
def export_activity():
    from flask import make_response
    from datetime import datetime
    entries = ActivityLog.query.order_by(ActivityLog.created_at.asc()).all()
    if not entries:
        return jsonify({'success': False, 'error': 'No entries to export'}), 400
    lines = [f"{e.created_at.replace(tzinfo=timezone.utc).astimezone(DUBAI_TZ).strftime('%d-%m-%Y-%H-%M')} | {e.user.name if e.user else 'System'} | {e.description}" for e in entries]
    content = '\n'.join(lines)
    filename = f"activity-log-{datetime.now().strftime('%d-%m-%Y-%H-%M')}.txt"
    response = make_response(content)
    response.headers['Content-Type'] = 'text/plain'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@admin_bp.route('/admin/api/activity/clear', methods=['POST'])
@login_required
@admin_required
def clear_activity():
    ActivityLog.query.delete()
    db.session.commit()
    log_activity('log_cleared', f'Activity log wiped by {current_user.name}', user=current_user)
    return jsonify({'success': True})

@admin_bp.route('/admin/api/activity/<int:entry_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_activity(entry_id):
    entry = ActivityLog.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    return jsonify({'success': True})


# ── Design Types ─────────────────────────────────────────────────────────────

@admin_bp.route('/admin/api/design-types', methods=['GET'])
@login_required
@admin_required
def list_design_types():
    types = DesignType.query.order_by(DesignType.name).all()
    return jsonify([{'id': t.id, 'name': t.name, 'team': t.team} for t in types])

@admin_bp.route('/admin/api/design-types', methods=['POST'])
@login_required
@admin_required
def create_design_type():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    team = (data.get('team') or '').strip() or None
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    if DesignType.query.filter_by(name=name).first():
        return jsonify({'error': 'Already exists'}), 409
    t = DesignType(name=name, team=team)
    db.session.add(t)
    db.session.commit()
    log_activity('design_type_created', f'Design type "{name}" created', user=current_user)
    return jsonify({'id': t.id, 'name': t.name, 'team': t.team})

@admin_bp.route('/admin/api/design-types/<int:type_id>', methods=['PATCH'])
@login_required
@admin_required
def update_design_type(type_id):
    t = DesignType.query.get_or_404(type_id)
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    t.name = name
    if 'team' in data:
        t.team = (data.get('team') or '').strip() or None
    db.session.commit()
    return jsonify({'id': t.id, 'name': t.name, 'team': t.team})

@admin_bp.route('/admin/api/design-types/<int:type_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_design_type(type_id):
    t = DesignType.query.get_or_404(type_id)
    name = t.name
    db.session.delete(t)
    db.session.commit()
    log_activity('design_type_deleted', f'Design type "{name}" deleted', user=current_user)
    return jsonify({'success': True})


# ── Design Directions ────────────────────────────────────────────────────────

@admin_bp.route('/admin/api/design-directions', methods=['GET'])
@login_required
@admin_required
def list_design_directions():
    dirs = DesignDirection.query.order_by(DesignDirection.name).all()
    return jsonify([{'id': d.id, 'name': d.name} for d in dirs])

@admin_bp.route('/admin/api/design-directions', methods=['POST'])
@login_required
@admin_required
def create_design_direction():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    if DesignDirection.query.filter_by(name=name).first():
        return jsonify({'error': 'Already exists'}), 409
    d = DesignDirection(name=name)
    db.session.add(d)
    db.session.commit()
    log_activity('design_direction_created', f'Design direction "{name}" created', user=current_user)
    return jsonify({'id': d.id, 'name': d.name})

@admin_bp.route('/admin/api/design-directions/<int:dir_id>', methods=['PATCH'])
@login_required
@admin_required
def update_design_direction(dir_id):
    d = DesignDirection.query.get_or_404(dir_id)
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    d.name = name
    db.session.commit()
    return jsonify({'id': d.id, 'name': d.name})

@admin_bp.route('/admin/api/design-directions/<int:dir_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_design_direction(dir_id):
    d = DesignDirection.query.get_or_404(dir_id)
    name = d.name
    db.session.delete(d)
    db.session.commit()
    log_activity('design_direction_deleted', f'Design direction "{name}" deleted', user=current_user)
    return jsonify({'success': True})


# ── CS quick-add (Design Types + Directions) ─────────────────────────────────

@admin_bp.route('/admin/api/design-types/quick-add', methods=['POST'])
@login_required
def quick_add_design_type():
    """CS, management and admin can quickly add a design type from the brief form."""
    if current_user.role not in ('admin', 'cs', 'management'):
        return jsonify({'error': 'Forbidden'}), 403
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    existing = DesignType.query.filter_by(name=name).first()
    if existing:
        return jsonify({'id': existing.id, 'name': existing.name})
    t = DesignType(name=name)
    db.session.add(t)
    db.session.commit()
    return jsonify({'id': t.id, 'name': t.name})

@admin_bp.route('/admin/api/design-directions/quick-add', methods=['POST'])
@login_required
def quick_add_design_direction():
    """CS, management and admin can quickly add a design direction from the brief form."""
    if current_user.role not in ('admin', 'cs', 'management'):
        return jsonify({'error': 'Forbidden'}), 403
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    existing = DesignDirection.query.filter_by(name=name).first()
    if existing:
        return jsonify({'id': existing.id, 'name': existing.name})
    d = DesignDirection(name=name)
    db.session.add(d)
    db.session.commit()
    return jsonify({'id': d.id, 'name': d.name})


# ── Dev Tools ────────────────────────────────────────────────────────────────
# These routes are gated by DEV_TOOLS_ENABLED in config.py.
# That flag must NEVER be set on the production server.
# Double-gated: even if someone hits the URL directly on prod, the config check
# returns 403 before any data is touched.

@admin_bp.route('/admin/api/dev/wipe-projects', methods=['POST'])
@login_required
@admin_required
def dev_wipe_projects():
    """
    DEV ONLY — wipes every project and all related data, then resets the
    FOC job number counter (which is computed from existing rows, so wiping
    projects automatically brings it back to FOC-001).

    WHY TRUNCATE CASCADE instead of Project.query.delete():
      .query.delete(synchronize_session=False) issues a raw SQL
      DELETE FROM projects, which bypasses SQLAlchemy's ORM cascade logic.
      PostgreSQL then enforces FK constraints on every child table
      (project_designers, deliverables, project_customers, notifications, etc.)
      and raises a ForeignKeyViolation error.

      TRUNCATE projects CASCADE tells Postgres to truncate the projects table
      AND every table that has a FK pointing at it — all in one atomic
      operation, with no explicit ordering needed.
    """
    from flask import current_app
    from sqlalchemy import text

    # Guard: refuse entirely if the dev tools flag is off — this is the
    # server-side safety net independent of whether the UI is shown.
    if not current_app.config.get('DEV_TOOLS_ENABLED'):
        return jsonify({'error': 'Dev tools are not enabled on this server'}), 403

    # TRUNCATE projects CASCADE:
    #   - Wipes the projects table.
    #   - Automatically cascades to all tables with a FK referencing projects:
    #     project_designers, project_customers, project_regions, deliverables,
    #     deliverable_assignments, brief_flags, brief_flag_messages,
    #     project_files, project_submissions, project_revisions,
    #     project_posm_channels, project_posm_customers, and notifications
    #     (where project_id is not null).
    #   - RESTART IDENTITY resets any auto-increment sequences on those tables
    #     back to 1 — keeps IDs tidy for a fresh dev environment.
    db.session.execute(text('TRUNCATE TABLE projects RESTART IDENTITY CASCADE'))
    db.session.commit()

    # The FOC counter is computed from existing job_number values
    # (see generate_job_number in projects.py), so it resets to FOC-001
    # automatically now that the projects table is empty.
    return jsonify({'success': True, 'message': 'All projects wiped. FOC counter reset.'})


@admin_bp.route('/admin/api/broadcast-update', methods=['POST'])
@login_required
@admin_required
def broadcast_update():
    """
    Fire a one-off update announcement email + in-app notification to every
    active user. Called from the admin panel.

    Expected JSON body:
    {
      "version":     "v1.2",
      "subject":     "Vitamin-E has been updated — v1.3",
      "intro":       "Vitamin-E v1.3 is now live. ...",
      "blog_url":    "https://app.vitamin-e.work/blog-post1-v1.2update"
    }
    """
    data = request.get_json(silent=True) or {}

    version  = data.get('version',  'v1.2')
    subject  = data.get('subject',  f'[Vitamin-E] App Update — {version}')
    intro    = data.get('intro',    'A new update is live on Vitamin-E.')
    blog_url = data.get('blog_url', 'https://app.vitamin-e.work/blog-post1-v1.2update')

    sent = broadcast_update_email(
        version=version,
        subject_line=subject,
        intro_line=intro,
        blog_url=blog_url
    )
    return jsonify({'success': True, 'sent': sent})