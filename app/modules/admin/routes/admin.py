import os
import uuid
from datetime import timezone, timedelta
from flask import Blueprint, jsonify, session, url_for, request
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import (
    User, JobRole, Client, Customer, Project,
    DeliverableType, DeliverableTypeDiscipline,
    DesignType, DesignDirection, ActivityLog, NotificationSound
)
from app.modules.admin.lib import accounts as account_rules
from app.modules.core.shared.lib.utils import log_activity
from app.modules.core.shared.lib.profilepic import save_profile_pic, delete_profile_pic, AVATAR_FOLDER
from app.modules.core.shared.lib.capabilities import can, require, require_api
from werkzeug.security import generate_password_hash

DUBAI_TZ = timezone(timedelta(hours=4))

admin_bp = Blueprint('admin', __name__)

# Every admin-panel API route gates on admin_panel, checked against the real
# logged-in user so an admin previewing as someone else keeps their own tools.
admin_required = require_api('admin_panel', real_user=True)

@admin_bp.route('/admin/api/users', methods=['GET'])
@login_required
@admin_required
def list_users():
    users = (User.query.options(joinedload(User.job_role), joinedload(User.reports_to))
             .order_by(User.name).all())
    return jsonify([account_rules.user_json(u) for u in users])


@admin_bp.route('/admin/api/org-options', methods=['GET'])
@login_required
@admin_required
def org_options():
    """Departments, seniority levels, job titles and teams for the account forms."""
    return jsonify(account_rules.org_options())

@admin_bp.route ('/admin/emulate/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def start_emulation(user_id):
    user = User.query.get_or_404(user_id)
    # About the target account, not the caller: an admin account is never a
    # valid emulation target.
    if user.is_admin:
        return jsonify({'success': False, 'error': 'Cannot emulate an admin account'}), 400
    if not user.is_active:
        return jsonify({'success': False, 'error': 'Cannot emulate a deactivated account'}), 400
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
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip()
    password = (data.get('password') or '').strip()

    if not all([name, email, password]):
        return jsonify({'success': False, 'error': 'Name, email and password are required'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'error': 'Email already exists'}), 400

    user = User(name=name, email=email, password_hash=generate_password_hash(password))
    try:
        changes = account_rules.apply_org_fields(user, data, current_user)
    except account_rules.AccountError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    db.session.add(user)
    db.session.commit()
    log_activity('user_created', f'User "{user.name}" created ({"; ".join(changes) or "no org fields"})',
                 user=current_user, entity_type='user', entity_name=user.name, entity_id=user.id)
    return jsonify({'success': True, 'user': account_rules.user_json(user)})

# Absolute (app/static/sounds) so saves don't depend on the working directory.
SOUND_UPLOAD_FOLDER = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'static', 'sounds'))
ALLOWED_SOUND_EXTENSIONS = {'mp3', 'wav', 'ogg', 'm4a', 'aac'}

@admin_bp.route('/admin/api/sounds', methods=['GET'])
@login_required
@admin_required
def list_sounds():
    """All uploaded notification sounds, newest first."""
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
    """Upload a notification sound file."""
    name = (request.form.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Please provide a name for this sound'}), 400

    if 'file' not in request.files or request.files['file'].filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    file = request.files['file']
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_SOUND_EXTENSIONS:
        return jsonify({'success': False, 'error': f'File type .{ext} not allowed'}), 400

    # Short uuid prefix so two uploads with the same name never overwrite each other.
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
    """Delete a notification sound: the DB row and the file on disk."""
    sound = NotificationSound.query.get_or_404(sound_id)
    name = sound.name  # read before delete; attributes expire on commit

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
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip()
    password = (data.get('password') or '').strip()

    if not name or not email:
        return jsonify({'success': False, 'error': 'Name and email are required'}), 400
    existing = User.query.filter_by(email=email).first()
    if existing and existing.id != user_id:
        return jsonify({'success': False, 'error': 'That email is already in use'}), 400

    try:
        changes = account_rules.apply_org_fields(user, data, current_user)
    except account_rules.AccountError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    user.name = name
    user.email = email
    if password:
        user.set_password(password)
    db.session.commit()
    if changes:
        log_activity('user_org_changed', f'{current_user.name} changed "{user.name}": {"; ".join(changes)}',
                     user=current_user, entity_type='user', entity_name=user.name, entity_id=user.id)
    return jsonify({'success': True, 'user': account_rules.user_json(user)})


@admin_bp.route('/admin/api/job-titles', methods=['GET'])
@login_required
@admin_required
def list_job_titles():
    return jsonify(account_rules.job_titles_json())


@admin_bp.route('/admin/api/job-titles/<int:title_id>', methods=['PATCH'])
@login_required
@admin_required
def update_job_title(title_id):
    """Rename a job title, or hide or show it in the pickers."""
    row = JobRole.query.get_or_404(title_id)
    try:
        account_rules.update_job_title(row, request.get_json(silent=True) or {})
    except account_rules.AccountError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    db.session.commit()
    log_activity('job_title_updated', f'{current_user.name} updated job title "{row.title}"', user=current_user)
    return jsonify({'success': True})


@admin_bp.route('/admin/api/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def admin_reset_password(user_id):
    """Set a random temporary password and return it once, for the admin to pass on."""
    from app.modules.auth.routes.auth import generate_temp_password
    user = User.query.get_or_404(user_id)
    temp_password = generate_temp_password()
    user.set_password(temp_password)
    db.session.commit()
    return jsonify({'success': True, 'temp_password': temp_password})


@admin_bp.route('/admin/api/users/<int:user_id>/active', methods=['POST'])
@login_required
@admin_required
def set_user_active(user_id):
    """Activate or deactivate an account. Body: {"active": true|false}.
    A deactivated user keeps their DB row (so project links still resolve) but
    cannot log in and drops out of user pickers."""
    if user_id == current_user.id:
        return jsonify({'success': False, 'error': 'Cannot deactivate your own account'}), 400
    user = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}
    user.is_active = bool(data.get('active'))
    db.session.commit()
    verb = 'reactivated' if user.is_active else 'deactivated'
    log_activity('user_' + ('activated' if user.is_active else 'deactivated'),
                 f'{current_user.name} {verb} account "{user.name}"',
                 user=current_user, entity_type='user', entity_name=user.name, entity_id=user.id)
    return jsonify({'success': True, 'is_active': user.is_active})


@admin_bp.route('/admin/api/users/<int:user_id>/avatar', methods=['POST'])
@login_required
@admin_required
def set_user_avatar(user_id):
    """Set or replace any user's profile photo, deactivated users included."""
    user = User.query.get_or_404(user_id)
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    stored_filename = save_profile_pic(request.files['file'], AVATAR_FOLDER)
    if not stored_filename:
        return jsonify({'success': False, 'error': 'Invalid file'}), 400

    delete_profile_pic(AVATAR_FOLDER, user.avatar_filename)
    user.avatar_filename = stored_filename
    user.avatar_step_completed = True
    db.session.commit()
    log_activity('user_avatar_set', f'{current_user.name} updated the photo for "{user.name}"',
                 user=current_user, entity_type='user', entity_name=user.name, entity_id=user.id)
    return jsonify({'success': True, 'url': url_for('static', filename=f'avatars/{stored_filename}')})


@admin_bp.route('/admin/api/users/<int:user_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_user(user_id):
    from sqlalchemy.exc import IntegrityError

    if user_id == current_user.id:
        return jsonify({'success': False, 'error': 'Cannot delete your own account'}), 400

    user = User.query.get_or_404(user_id)

    # Refused while the user is on NOT NULL project columns; the admin must
    # reassign or delete those projects first.
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
        # Name the table still holding a reference, when it is a known one.
        msg = str(exc.orig) if hasattr(exc, 'orig') else str(exc)
        table = 'unknown table'
        # Substring match, so 'projects' stays last ('chat_tray_projects' holds it).
        for t_name in ['project_files', 'project_submissions', 'project_revisions',
                        'brief_flags', 'brief_flag_messages', 'blog_posts',
                        'feature_requests', 'bug_reports', 'deliverable_assignments',
                        'clients', 'chat_tray_projects',
                        'decision_flags', 'decision_flag_messages',
                        'deliverable_preproduction_events', 'deliverable_status_logs',
                        'deliverables', 'friction_log_entries', 'notification_sounds',
                        'project_activity_seen', 'project_customer_status_logs',
                        'project_customers', 'project_edit_access_requests',
                        'project_note_reactions', 'project_notes', 'project_overlay_views',
                        'project_status_logs', 'project_submission_events',
                        'project_submission_files', 'project_table_views', 'site_visits',
                        'technical_submissions', 'user_achievements',
                        'user_display_settings', 'user_pinned_achievements',
                        'user_table_layouts', 'projects']:
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

    # Refused while in use: projects (directly or via one of its contacts) and
    # deliverable types hold FKs that can't be nulled or cascaded safely.
    contact_ids = [c.id for c in client.contacts]
    project_filter = Project.client_id == client_id
    if contact_ids:
        project_filter = project_filter | Project.contact_id.in_(contact_ids)
    project_count = Project.query.filter(project_filter).count()
    if project_count:
        return jsonify({'success': False,
                        'error': f'"{name}" is used by {project_count} project(s). '
                                 f'Move or delete those projects before deleting the client.'}), 400

    type_count = DeliverableType.query.filter_by(client_id=client_id).count()
    if type_count:
        return jsonify({'success': False,
                        'error': f'"{name}" has {type_count} deliverable type(s). '
                                 f'Delete those before deleting the client.'}), 400

    # Contacts belong only to this client (client_id is NOT NULL), so they go with it.
    for contact in client.contacts:
        db.session.delete(contact)
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
    from flask import current_app

    project = Project.query.get_or_404(project_id)
    name = project.name

    # Remove reference files from disk; the DB rows go by cascade.
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
    # job_number is shown so the admin can tell which number a delete frees.
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
    # Deleting the row also frees its unique job_number.
    db.session.delete(draft)
    db.session.commit()
    log_activity('draft_deleted', f'Draft "{name}" deleted', user=current_user, entity_type='project', entity_name=name)
    return jsonify({'success': True})


# ── Job Numbers ────────────────────────────────────────────────────────────────
# Lists projects with a job number and clears one (sets it to NULL) without
# deleting the project, so an abandoned draft's number can be reused.

@admin_bp.route('/admin/api/job-numbers', methods=['GET'])
@login_required
@admin_required
def list_job_numbers():
    """Every project with a job_number, sorted by number."""
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
    """Set a project's job_number to NULL so the number can be reused.
    The project itself is kept."""
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
    # File fields change only when their key is sent; a missing key means
    # "leave alone", so a plain name edit does not wipe the image.
    if 'reference_image' in data:
        dt.reference_image = data['reference_image'] # a filename, or None to clear it  
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
    """Upload a deliverable type's template file to app/file_templates/ (local
    disk, not the NAS) and return its filename. The caller then sends that
    filename in the create/update request, as with the reference image below."""
    from app.modules.core.shared.lib.paths import template_upload_folder

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext != 'ai':
        return jsonify({'success': False, 'error': 'Only .ai files are supported'}), 400

    stored_filename = f'{uuid.uuid4().hex[:8]}.{ext}'
    os.makedirs(template_upload_folder(), exist_ok=True)
    file.save(os.path.join(template_upload_folder(), stored_filename))

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
    category = request.args.get('category', '').strip()  # a CATEGORY_KEYWORDS key, 'other' or 'all'

    # Category -> substrings matched against ActivityLog.action. "other" (below)
    # matches actions that hit none of them.
    CATEGORY_KEYWORDS = {
        'creation':    ['created', 'uploaded', 'added', 'internal_review_submitted', 'submission_uploaded'],
        'flags':       ['flagged', 'submission_flagged'],
        'deletions':   ['deleted'],
        'assignments': ['assigned'],
        'edits':       ['updated', 'changed', 'status_changed', 'deliverable_status_changed',
                        'submitted_to_client', 'internal_review_submitted'],
    }
    ALL_NAMED_KEYWORDS = [kw for kws in CATEGORY_KEYWORDS.values() for kw in kws]

    if search:
        pattern = f'%{search}%'
        query = query.filter(
            db.or_(
                ActivityLog.description.ilike(pattern),
                ActivityLog.entity_name.ilike(pattern)
            )
        )
    try:
        from_dt = datetime.fromisoformat(from_date) if from_date else None
        to_dt = datetime.fromisoformat(to_date + ' 23:59:59') if to_date else None
    except ValueError:
        return jsonify({'success': False, 'error': 'Dates must be YYYY-MM-DD'}), 400
    if from_dt:
        query = query.filter(ActivityLog.created_at >= from_dt - timedelta(hours=4))
    if to_dt:
        query = query.filter(ActivityLog.created_at <= to_dt - timedelta(hours=4))

    if category and category != 'all':
        cat_lower = category.lower()
        if cat_lower == 'other':
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


# ── Dev Tools ────────────────────────────────────────────────────────────────
# Gated by DEV_TOOLS_ENABLED in config.py, which must NEVER be set in
# production. The route checks the flag itself, so a direct call on prod gets 403.

@admin_bp.route('/admin/api/dev/wipe-projects', methods=['POST'])
@login_required
@admin_required
def dev_wipe_projects():
    """DEV ONLY: wipe every project and all related rows.
    Uses TRUNCATE ... CASCADE because a bulk Project.query.delete() skips the
    ORM cascades and fails on child-table foreign keys."""
    from flask import current_app
    from sqlalchemy import text

    # Server-side guard, whether or not the UI is shown.
    if not current_app.config.get('DEV_TOOLS_ENABLED'):
        return jsonify({'error': 'Dev tools are not enabled on this server'}), 403

    # CASCADE also empties every table with a FK to projects (deliverables,
    # submissions, flags, files, notifications, ...); RESTART IDENTITY resets
    # their ID sequences to 1.
    db.session.execute(text('TRUNCATE TABLE projects RESTART IDENTITY CASCADE'))
    db.session.commit()

    # generate_job_number derives the FOC counter from existing rows, so it
    # restarts at FOC-001 with no extra step.
    return jsonify({'success': True, 'message': 'All projects wiped. FOC counter reset.'})


# ─────────────────────────────────────────────────────────────────────────
# Deliverable-type reference image upload
#
# Used by the admin panel's Deliverable Types form (admin.js). Gated on
# manage_reference_data, which is wider than admin_panel (CS, management).
# ─────────────────────────────────────────────────────────────────────────

@admin_bp.route('/projects/deliverable-types/upload-image', methods=['POST'])
@login_required
@require('manage_reference_data', real_user=True)
def upload_deliverable_type_image():
    """Save a deliverable type's reference image and return its filename.
    No DB write: the caller sends the filename in its create/update request."""
    from flask import current_app

    file = request.files.get('file')
    if not file:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in {'jpg', 'jpeg', 'png', 'gif', 'webp'}:
        return jsonify({'success': False, 'error': 'File type not allowed'}), 400

    filename = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = os.path.join(current_app.root_path, 'static', 'deliverable-images')
    os.makedirs(upload_dir, exist_ok=True)
    file.save(os.path.join(upload_dir, filename))

    return jsonify({'success': True, 'filename': filename})
