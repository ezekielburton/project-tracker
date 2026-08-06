from datetime import datetime, timezone, timedelta
import re
from flask import send_file, abort
from flask import (Blueprint, request, current_app, send_from_directory,
                   jsonify, session, url_for)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import (Project, User, Customer, ProjectCustomer, Deliverable,
                        DeliverableAssignment, ProjectSubmission,
                        ProjectSubmissionDeliverable, ProjectSubmissionFile, ProjectRevision,
                        ProjectRevisionDeliverable, ProjectPosmChannel, ProjectFile,
                        ProjectRegion)
from app.decorators import role_required
from app.notifications import (
    notify_cs_of_revision_submitted, create_notification,
    notify_of_submission_to_client, notify_team_leads_of_new_project
)
from app.utils import log_activity, file_type_label
from app.achievements import check_achievements
from app.status_tracking import record_project_status, record_customer_status, record_deliverable_status

submission_bp = Blueprint('submission', __name__)

@submission_bp.route('/projects/submit', methods=['POST'])
@login_required
@role_required('cs', 'admin', 'management')
def submit_project():
    try:
        data = request.get_json()

        print(f"Draft ID received: {data.get('draft_id')}")
        print(f"Current user ID: {current_user.id}")

        # ── Basic validation ─────────────────────────────────
        required_fields = ['name', 'client_id', 'cs_lead_id', 'brief_type']
        for field in required_fields:
          if not data.get(field):
             return jsonify({'error': f'Missing required field: {field}'}), 400

        # ── Parse dates ──────────────────────────────────────
        from datetime import datetime
        def parse_date(val):
            if not val:
                return None
            try:
                return datetime.strptime(val, '%Y-%m-%d').date()
            except ValueError:
                return None

        # ── Promote draft to active, or create fresh ─────────
        draft_id = data.get('draft_id')
        project = None

        if draft_id:
            candidate = Project.query.get(int(draft_id))
            if candidate and candidate.created_by_id == current_user.id and candidate.project_status == 'draft':
                project = candidate

        if not project:
            project = Project(creator=current_user)
            db.session.add(project)
            is_new = True
        else:
            is_new = project.project_status == 'draft'  # True if promoting from draft

        project.name = data['name'].strip()

        # ── Duplicate name guard ─────────────────────────────
        # Block submission if any non-draft project (including approved ones)
        # already has this name. Checked BEFORE flush/commit so no NAS folders
        # are created if it fails.
        _name_q = Project.query.filter(
            Project.name.ilike(project.name),
            Project.project_status != 'draft'
        )
        if project.id:
            _name_q = _name_q.filter(Project.id != project.id)
        if _name_q.first():
            return jsonify({'error': f'A project named "{project.name}" already exists. Please choose a different name.'}), 400

        project.client_id = int(data['client_id'])
        project.cs_lead_id = int(data['cs_lead_id'])
        job_num = data.get('job_number')
        if job_num:
            conflict = Project.query.filter(
                Project.job_number == job_num,
                Project.id != project.id
            ).first()
            if conflict:
                return jsonify({'error': f'Job number {job_num} is already in use'}), 400
        project.job_number = job_num
        project.design_teams_requested = ','.join(data.get('design_teams', []))
        project.brief_type = data['brief_type']
        project.urgency = data.get('urgency')
        project.required_output = data.get('required_output')
        project.campaign_notes = data.get('concept_requirements')
        project.concept_deadline = parse_date(data.get('concept_deadline'))
        raw_cdt = data.get('concept_deadline_time')
        project.concept_deadline_time = datetime.strptime(raw_cdt, '%H:%M').time() if raw_cdt else None
        project.has_concept = bool(data.get('has_concept', False))
        project.concept_options_required = data.get('concept_options_required')
        project.has_kv = bool(data.get('has_kv', False))
        project.kv_requirements = data.get('kv_requirements')
        project.kv_deadline = parse_date(data.get('kv_deadline'))
        project.kv_options_required = data.get('kv_options_required')
        project.briefing_date = parse_date(data.get('briefing_date'))
        project.first_output_deadline = parse_date(data.get('first_output_deadline'))
        project.execution_date = parse_date(data.get('final_deadline'))
        project.installation_date = parse_date(data.get('installation_date'))

        # ── Standard brief fields ────────────────────────────
        if data['brief_type'] == 'standard':
            from app.models import DesignType, DesignDirection
            project.design_type_id = int(data['design_type_id']) if data.get('design_type_id') else None
            project.design_direction_id = int(data['design_direction_id']) if data.get('design_direction_id') else None
            project.client_expectation = data.get('client_expectation')
            project.what_to_avoid = data.get('what_to_avoid')
            project.additional_information = data.get('additional_information')

        db.session.flush()

        # First-ever status for this project — needs the flush above so
        # project.id exists (record_project_status needs it for the log row).
        # Also correctly handles a promoted draft: closes whatever status log
        # row the draft had open (if any) and opens a fresh 'briefed' one.
        record_project_status(project, 'briefed', current_user)

        if data['brief_type'] == 'standard':
            for del_item in data.get('standard_deliverables', []):
                if isinstance(del_item, str):
                    del_name = del_item.strip()
                    del_deadline = None
                    del_teams = None
                else:
                    del_name = (del_item.get('name') or '').strip()
                    raw_dd = del_item.get('design_deadline')
                    del_deadline = datetime.strptime(raw_dd, '%Y-%m-%d').date() if raw_dd else None
                    raw_time = del_item.get('design_deadline_time')
                    del_time = datetime.strptime(raw_time, '%H:%M').time() if raw_time else None
                    raw_teams = del_item.get('teams') or []
                    del_teams = ','.join(raw_teams) if raw_teams else None
                if not del_name:
                    continue
                deliverable = Deliverable(
                    project_id=project.id,
                    project_customer_id=None,
                    deliverable_type_id=None,
                    name=del_name,
                    design_deadline=del_deadline,
                    design_deadline_time=del_time,
                    teams=del_teams,
                    status='in_queue',
                    created_by=current_user
                )
                db.session.add(deliverable)
                db.session.flush()  # need deliverable.id for the status log row
                record_deliverable_status(deliverable, 'in_queue', current_user)
        else:
            # ── Create regions ───────────────────────────────────
            ProjectRegion.query.filter_by(project_id=project.id).delete()
            for region_name in data['regions']:
                region = ProjectRegion(
                    project_id=project.id,
                    region=region_name
                )
                db.session.add(region)

            # ── Create customers and deliverables ────────────────
            for pc in ProjectCustomer.query.filter_by(project_id=project.id).all():
                db.session.delete(pc)
            db.session.flush()

            customer_map = {}
            for item in data['deliverables']:
                customer_id = int(item['customer_id'])

                if customer_id not in customer_map:
                    customer_dates = data.get('customer_dates', {})
                    dates = customer_dates.get(str(customer_id), {})
                    raw_time = dates.get('design_deadline_time')
                    project_customer = ProjectCustomer(
                        project_id=project.id,
                        customer_id=customer_id,
                        design_deadline=datetime.strptime(dates['design_deadline'], '%Y-%m-%d').date() if dates.get('design_deadline') else None,
                        design_deadline_time=datetime.strptime(raw_time, '%H:%M').time() if raw_time else None,
                        installation_date=datetime.strptime(dates['installation_date'], '%Y-%m-%d').date() if dates.get('installation_date') else None,
                        status='briefed'
                    )
                    db.session.add(project_customer)
                    db.session.flush()
                    record_customer_status(project_customer, 'briefed', current_user)
                    customer_map[customer_id] = project_customer.id

                deliverable = Deliverable(
                    project_id=project.id,
                    project_customer_id=customer_map[customer_id],
                    deliverable_type_id=int(item['type_id']) if item.get('type_id') and item['type_id'] != 'custom' else None,
                    name=item['name'],
                    created_by=current_user,
                    status='in_queue'
                )
                db.session.add(deliverable)
                db.session.flush()  # need deliverable.id for the status log row
                record_deliverable_status(deliverable, 'in_queue', current_user)

        db.session.commit()
        # --- NAS Folder Creation ------
        print(f'NAS check: is_new={is_new}, project_id={project.id}')
        if is_new:
            from flask import current_app as _app
            from app.nas import _run_in_background, create_project_folders
            from app.models import Project as _Project
            _pid = project.id
            _app_obj = _app._get_current_object()
            _run_in_background(_app_obj, lambda: create_project_folders(
                _Project.query.get(_pid)
            ))

        # ── FOC conflict check ────────────────────────────────────
        # A draft can sit for a long time. By the time it's submitted,
        # another project may have claimed the same FOC number. If that
        # happens we silently reassign the next available number and
        # signal the client to show a toast explaining the change.
        job_number_changed = False
        old_job_number = None
        import re as _re
        if project.job_number and _re.match(r'^FOC-\d+$', project.job_number):
            conflict = Project.query.filter(
                Project.job_number == project.job_number,
                Project.id != project.id,
                Project.project_status != 'draft'
            ).first()
            if conflict:
                # Reuse the same generation logic as generate_job_number
                FOC_PAD = 3
                existing = Project.query.with_entities(Project.job_number).filter(
                    Project.job_number.like('FOC-%')
                ).all()
                used_numbers = []
                for (jn,) in existing:
                    suffix = jn[4:]
                    if suffix.isdigit():
                        used_numbers.append(int(suffix))
                next_num = (max(used_numbers) + 1) if used_numbers else 1
                old_job_number = project.job_number
                project.job_number = 'FOC-' + str(next_num).zfill(FOC_PAD)
                db.session.commit()
                job_number_changed = True

        # Notifications (non-blocking)
        try:
            selected_cs_id = int(data['cs_lead_id'])
            # Skip CS lead notification if they are the one submitting, OR if they created
            # the project — in both cases they already know they own it.
            if selected_cs_id != current_user.id and selected_cs_id != project.created_by_id:
                cs_lead = User.query.get(selected_cs_id)
                if cs_lead:
                    create_notification(
                        recipient=cs_lead,
                        message=f'You have been assigned as CS Lead on "{project.name}".',
                        notification_type='project_assigned',
                        project=project,
                        triggered_by=current_user
                    )

            # Notify all team members (leads + designers) on every requested team.
            # Uses design_teams_requested from the submitted form, which is reliable for both
            # standard and C&CM briefs. Replaces the old disciplines_used approach, which could
            # miss teams when deliverables had no type_id (e.g. custom deliverables).
            teams_requested = data.get('design_teams', [])
            if teams_requested:
                notify_team_leads_of_new_project(
                    project=project,
                    teams_requested=teams_requested,
                    triggered_by=current_user
                )
        except Exception as notif_err:
            import traceback
            traceback.print_exc()

        log_activity('project_submitted', f'Project "{project.name}" submitted', user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)
        check_achievements(current_user, 'project_submitted')

        return jsonify({
            'success': True,
            'project_id': project.id,
            'redirect_url': '/',
            'job_number_changed': job_number_changed,
            'old_job_number': old_job_number,
            'new_job_number': project.job_number if job_number_changed else None,
        }), 201

    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Something went wrong. Please try again.'}), 500


# ── Standard Brief Deliverables ───────────────────────────────────────────────

@submission_bp.route('/projects/<int:project_id>/submission/upload', methods=['POST'])
@login_required
@role_required('admin', 'designer', 'team_lead')  # CS can view submissions but not upload
def upload_submission(project_id):
    """Designer uploads a new client deck (PDF or PPTX).
    - Deactivates any previous active submission.
    - If the previous deck was never submitted to the client, its physical file is deleted (draft only).
    - If it was submitted to the client, the file is kept for audit history.
    - Returns the new submission ID and the deliverable IDs from the previous submission
      so the frontend can pre-check the deliverable picker."""
    from app.models import ProjectSubmission
    import os

    project = Project.query.get_or_404(project_id)


    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    # Only PDF and PPTX are valid client decks
    allowed = {'pdf', 'pptx', 'docx', 'doc'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed:
        return jsonify({'success': False, 'error': 'Only PDF and PPTX files are accepted'}), 400
    
    file_bytes = file.read()

    # Channel-aware upload: if posm_channel_id is present, only deactivate the
    # previous submission for THAT channel, not all active submissions.
    posm_channel_id = request.form.get('posm_channel_id', type=int)
    channel = None
    if posm_channel_id:
        from app.models import ProjectPosmChannel
        channel = ProjectPosmChannel.query.filter_by(
            id=posm_channel_id, project_id=project_id
        ).first()

    # Build query for the "previous active" submission scoped to the channel (or global)
    prev_q = ProjectSubmission.query.filter_by(project_id=project_id, is_active=True)
    if channel:
        prev_q = prev_q.filter_by(posm_country=channel.posm_country)
        if channel.posm_customer_id is not None:
            prev_q = prev_q.filter(ProjectSubmission.posm_customer_id == channel.posm_customer_id)
        else:
            prev_q = prev_q.filter(ProjectSubmission.posm_customer_id == None)  # noqa: E711
    else:
        # Non-channel uploads: deactivate any active submission (existing behaviour)
        pass

    previous = prev_q.first()

    # Collect the deliverable IDs that were included in the previous submission
    # so the picker can pre-populate the checkboxes for the designer
    previous_deliverable_ids = []
    if previous:
        previous_deliverable_ids = [
            link.deliverable_id for link in previous.included_deliverables
        ]
        # Only delete the physical file if this deck was never approved and sent to the client.
        # Approved decks are kept permanently for invoice / audit history.
        from app.nas import delete_app_file, build_file_path, _run_in_background
        _old_nas  = build_file_path(project, 'Submissions', previous.original_filename)
        _del_app  = current_app._get_current_object()
        _del_path = _old_nas
        _run_in_background(_del_app, lambda: delete_app_file(_del_path))
        previous.is_active = False

    # Set temporary file name
    stored_filename = f"pending.{ext}"

    submission = ProjectSubmission(
        project_id=project_id,
        filename=stored_filename,
        original_filename=file.filename,
        file_type=ext,
        uploaded_by_id=current_user.id,
        is_active=True,
        is_flagged=False,
        # Tag with channel context so channel-scoped queries find it
        posm_country=channel.posm_country if channel else None,
        posm_customer_id=channel.posm_customer_id if channel else None,
        phase='posm' if channel else 'concept_kv',
    )
    db.session.add(submission)

    # Auto-name the file with the canonical format at upload time
    def _sanitize(s):
        return re.sub(r'[\\/:*?"<>|]', '', s).strip()

    client_name = project.client_brand.name if project.client_brand else 'Client'
    GULF_REGION_NAMES = {
        'uae': 'UAE', 'kuwait': 'Kuwait',
        'qatar': 'Qatar', 'bahrain': 'Bahrain', 'oman': 'Oman'
    }

    if channel:
        country = channel.posm_country or ''
        if channel.posm_customer_id:
            from app.models import ProjectCustomer as _PC
            pc = _PC.query.get(channel.posm_customer_id)
            posm_rev = (pc.posm_revision_count or 0) if pc else 0
            posm_label = 'Initial' if posm_rev == 0 else f'Revision {posm_rev}'
            customer_name = pc.customer.name if (pc and pc.customer) else 'Customer'
            country_display = GULF_REGION_NAMES.get(country, country.title())
            submission.original_filename = (
                f'{_sanitize(client_name)} - {_sanitize(project.name)} - '
                f'{country_display} - {_sanitize(customer_name)} - POSM - {posm_label}.{ext}'
            )
        elif country:
            country_display = GULF_REGION_NAMES.get(country, country.title())
            counts = project.posm_country_revision_counts or {}
            posm_rev = counts.get(country, 0)
            posm_label = 'Initial' if posm_rev == 0 else f'Revision {posm_rev}'
            submission.original_filename = (
                f'{_sanitize(client_name)} - {_sanitize(project.name)} - '
                f'{country_display} - POSM - {posm_label}.{ext}'
            )
        else:
            is_revised = (project.revision_count or 0) > 0
            revision_label = 'Initial' if not is_revised else f'Revision {project.revision_count}'
            submission.original_filename = (
                f'{_sanitize(client_name)} - {_sanitize(project.name)} - POSM - {revision_label}.{ext}'
            )
    else:
        # C&CM projects: C&KV submissions get their own revision counter and label
        if project.brief_type == 'ccm':
            ckv_rev = project.ckv_revision_count or 0
            ckv_label = 'Initial' if ckv_rev == 0 else f'Revision {ckv_rev}'
            submission.original_filename = (
                f'{_sanitize(client_name)} - {_sanitize(project.name)} - '
                f'Concept & KV - {ckv_label}.{ext}'
            )
        else:
            # Standard briefs use the global revision_count
            is_revised = (project.revision_count or 0) > 0
            revision_label = 'Initial' if not is_revised else f'Revision {project.revision_count}'
            submission.original_filename = (
                f'{_sanitize(client_name)} - {_sanitize(project.name)} - {revision_label}.{ext}'
            )

    # Reset channel/project status after reupload so the picker state renders
    if channel and channel.status in ('internal_revision',):
        channel.status = 'in_queue'
    elif not channel and project.project_status == 'internal_revision':
        # Standard brief reupload after internal CS flag
        record_project_status(project, 'in_progress', current_user)
    elif not channel and project.concept_status in ('revision_in_queue', 'revision_in_progress', 'internal_revision'):
        # C&KV reupload after client revision or internal flag — reset so picker shows
        project.concept_status = 'in_progress'
        if project.kv_status in ('revision_in_queue', 'revision_in_progress', 'internal_revision'):
            project.kv_status = 'in_progress'
    
    # Commit immediately — never block the HTTP response on a NAS upload
    submission.filename = submission.original_filename
    db.session.commit()

    # Upload to NAS in background thread
    from app.nas import upload_app_file, build_file_path, _run_in_background
    _bg_folder      = build_file_path(project, 'Submissions', submission.original_filename).rsplit('/', 1)[0]
    _bg_bytes       = file_bytes
    _bg_filename    = submission.original_filename
    _bg_app         = current_app._get_current_object()
    _bg_uploader_id = current_user.id
    _bg_project_id  = project.id

    def _upload_submission_deck():
        try:
            upload_app_file(_bg_bytes, _bg_folder, _bg_filename)
        except RuntimeError:
            from app.models import User as _U, Project as _P
            from app.notifications import create_notification
            uploader = _U.query.get(_bg_uploader_id)
            proj     = _P.query.get(_bg_project_id)
            if uploader and proj:
                create_notification(
                    recipient=uploader,
                    message=(f'Your deck "{_bg_filename}" could not be saved to storage '
                             f'for "{proj.name}". Please try reuploading.'),
                    notification_type='nas_upload_failed',
                    project=proj,
                )

    _run_in_background(_bg_app, _upload_submission_deck)

    log_activity('submission_uploaded',
                 f'Client deck "{file.filename}" uploaded for "{project.name}" by {current_user.name}',
                 user=current_user, entity_type='project',
                 entity_name=project.name, entity_id=project.id)

    return jsonify({
        'success': True,
        'submission': {
            'id': submission.id,
            'original_filename': submission.original_filename,
            'file_type': submission.file_type,
            'uploaded_by': current_user.name
        },
        # Pre-populate the deliverable picker with whatever was selected last time
        'previous_deliverable_ids': previous_deliverable_ids
    })


@submission_bp.route('/projects/<int:project_id>/submission/submit-for-review', methods=['POST'])
@login_required
@role_required('admin', 'designer', 'team_lead')
def submit_for_internal_review(project_id):
    """Designer locks in which deliverables are included and sends the deck to CS for review.
    - Creates ProjectSubmissionDeliverable rows linking this submission to its deliverables.
    - Sets project status → internal_review.
    - Sets each included deliverable status → internal_review.
    - Notifies all CS / admin users."""
    from app.models import ProjectSubmission, ProjectSubmissionDeliverable

    project = Project.query.get_or_404(project_id)


    data = request.get_json() or {}
    submission_id = data.get('submission_id')
    deliverable_ids = data.get('deliverable_ids', [])
    includes_concept = bool(data.get('includes_concept', False))
    includes_kv = bool(data.get('includes_kv', False))
    posm_customer_id = data.get('posm_customer_id')
    posm_country     = (data.get('posm_country') or '').strip().lower() or None
    posm_channel_id  = data.get('posm_channel_id')

    if not submission_id:
        return jsonify({'success': False, 'error': 'No submission ID provided'}), 400
    if not deliverable_ids and not includes_concept and not includes_kv:
        return jsonify({'success': False, 'error': 'Select at least one item to include'}), 400

    # Make sure the submission belongs to this project and is active
    submission = ProjectSubmission.query.filter_by(
        id=submission_id, project_id=project_id, is_active=True
    ).first()
    if not submission:
        return jsonify({'success': False, 'error': 'Submission not found or no longer active'}), 400

    # Clear any previous deliverable links on this submission (safe to replace
    # if designer submits for review more than once without CS touching it)
    ProjectSubmissionDeliverable.query.filter_by(submission_id=submission.id).delete()

    # Resolve channel (POSM parallel flow)
    channel = None
    if posm_channel_id:
        from app.models import ProjectPosmChannel
        channel = ProjectPosmChannel.query.filter_by(
            id=int(posm_channel_id), project_id=project_id
        ).first()

    # Determine submission phase and Gulf/POSM context
    if channel:
        # Channel-aware POSM: metadata already tagged on the submission at upload time
        submission.phase = 'posm'
        channel.status = 'internal_review'
    elif posm_country:
        # Legacy Gulf POSM path (country provided without a channel object)
        from app.models import ProjectCustomer
        submission.posm_country = posm_country
        submission.phase = 'posm'
        if posm_customer_id:
            pc = ProjectCustomer.query.filter_by(
                id=int(posm_customer_id), project_id=project_id
            ).first()
            submission.posm_customer_id = pc.id if pc else None
        else:
            submission.posm_customer_id = None
        record_project_status(project, 'internal_review', current_user)
    else:
        submission.phase = 'concept_kv'
        submission.posm_country    = None
        submission.posm_customer_id = None
        # When the project has POSM channels, project status is driven by those channels.
        # C&KV is a parallel channel — don't overwrite project status here.
        if not project.posm_channels:
            record_project_status(project, 'internal_review', current_user)

    # Save concept/KV flags on the submission and advance their statuses (concept/KV phase only)
    submission.includes_concept = includes_concept
    submission.includes_kv = includes_kv
    if submission.phase == 'concept_kv':
        if includes_concept and project.has_concept:
            project.concept_status = 'internal_review'
        if includes_kv and project.has_kv:
            project.kv_status = 'internal_review'

    # Create a link row for each selected deliverable
    for d_id in deliverable_ids:
        deliverable = Deliverable.query.filter_by(id=d_id, project_id=project_id).first()
        if deliverable:
            link = ProjectSubmissionDeliverable(
                submission_id=submission.id,
                deliverable_id=d_id
            )
            db.session.add(link)
            # Move the deliverable into internal review (applies to both Standard and POSM flows)
            record_deliverable_status(deliverable, 'internal_review', current_user)

    db.session.commit()

    # Notify only the CS lead assigned to this project
    if project.cs_lead and project.cs_lead.id != current_user.id:
        create_notification(
            recipient=project.cs_lead,
            message=f'"{project.name}" has been submitted for internal review by {current_user.name}',
            notification_type='internal_review_submitted',
            project=project,
            triggered_by=current_user
        )

    log_activity('internal_review_submitted',
                 f'"{project.name}" submitted for internal review by {current_user.name} '
                 f'({len(deliverable_ids)} deliverable(s) included)',
                 user=current_user, entity_type='project',
                 entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})


@submission_bp.route('/projects/<int:project_id>/submission/flag', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def flag_submission(project_id):
    """CS flags the active deck with a revision note.
    - Sets project status → internal_revision.
    - Sets every deliverable that was included in this submission → internal_revision.
    - Notifies the designer who uploaded the deck."""
    from app.models import ProjectSubmission
    from datetime import datetime as dt

    project = Project.query.get_or_404(project_id)


    data = request.get_json() or {}
    message = (data.get('message') or '').strip()
    posm_channel_id = data.get('posm_channel_id')
    if not message:
        return jsonify({'success': False, 'error': 'Please provide a reason for flagging'}), 400

    from app.utils import strip_html
    plain_message = strip_html(message)

    # Resolve channel (POSM parallel flow)
    channel = None
    if posm_channel_id:
        from app.models import ProjectPosmChannel
        channel = ProjectPosmChannel.query.filter_by(
            id=int(posm_channel_id), project_id=project_id
        ).first()

    # Find the active submission — scoped to channel or global
    if channel:
        sub_q = ProjectSubmission.query.filter_by(
            project_id=project_id, is_active=True, posm_country=channel.posm_country
        )
        if channel.posm_customer_id is not None:
            sub_q = sub_q.filter(ProjectSubmission.posm_customer_id == channel.posm_customer_id)
        else:
            sub_q = sub_q.filter(ProjectSubmission.posm_customer_id == None)  # noqa: E711
    else:
        sub_q = ProjectSubmission.query.filter_by(project_id=project_id, is_active=True)
    submission = sub_q.first()
    if not submission:
        return jsonify({'success': False, 'error': 'No active submission to flag'}), 400

    # Mark the submission as flagged
    submission.is_flagged = True
    submission.flag_message = message
    submission.flagged_by_id = current_user.id
    submission.flagged_at = dt.utcnow()

    if channel:
        channel.status = 'internal_revision'
        # Push every included deliverable into internal_revision (POSM flow)
        for link in submission.included_deliverables:
            if link.deliverable:
                record_deliverable_status(link.deliverable, 'internal_revision', current_user)
    else:
        # Push project into internal_revision state
        record_project_status(project, 'internal_revision', current_user)
        # Push every included deliverable into internal_revision
        for link in submission.included_deliverables:
            if link.deliverable:
                record_deliverable_status(link.deliverable, 'internal_revision', current_user)
        # Push concept/KV too if they were included in this submission
        if submission.includes_concept:
            project.concept_status = 'internal_revision'
        if submission.includes_kv:
            project.kv_status = 'internal_revision'

    db.session.commit()

    # Notify the designer who uploaded the deck
    create_notification(
        recipient=submission.uploaded_by,
        message=f'Your client deck for "{project.name}" was flagged by CS: {plain_message}',
        notification_type='submission_flagged',
        project=project,
        triggered_by=current_user
    )

    log_activity('submission_flagged',
                 f'Client deck for "{project.name}" flagged by {current_user.name}: {plain_message}',
                 user=current_user, entity_type='project',
                 entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})


@submission_bp.route('/projects/<int:project_id>/submission/submit-to-client', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def submit_to_client(project_id):
    """CS approves the deck and marks it as submitted to the client.
    - Guards: must have an active, unflagged submission in internal_review state.
    - Stamps submitted_to_client_at on the submission (file is now kept permanently).
    - Increments project.revision_count.
    - Sets project status → submitted_to_client.
    - Sets ALL project deliverables → submitted_to_client.
    - Returns client email (if stored) and project name so the frontend can open a mailto prompt."""
    from app.models import ProjectSubmission
    from datetime import datetime as dt

    project = Project.query.get_or_404(project_id)


    data = request.get_json(silent=True) or {}
    posm_channel_id = data.get('posm_channel_id')

    # Resolve channel (POSM parallel flow)
    channel = None
    if posm_channel_id:
        from app.models import ProjectPosmChannel
        channel = ProjectPosmChannel.query.filter_by(
            id=int(posm_channel_id), project_id=project_id
        ).first()

    # Find the active submission — scoped to channel or global
    if channel:
        sub_q = ProjectSubmission.query.filter_by(
            project_id=project_id, is_active=True, posm_country=channel.posm_country
        )
        if channel.posm_customer_id is not None:
            sub_q = sub_q.filter(ProjectSubmission.posm_customer_id == channel.posm_customer_id)
        else:
            sub_q = sub_q.filter(ProjectSubmission.posm_customer_id == None)  # noqa: E711
        submission = sub_q.first()
        if not submission:
            return jsonify({'success': False, 'error': 'Upload a client deck before submitting'}), 400
        if submission.is_flagged:
            return jsonify({'success': False, 'error': 'The current deck is flagged — wait for the designer to reupload'}), 400
        if channel.status != 'internal_review':
            return jsonify({'success': False, 'error': 'Deck must be in Internal Review before submitting to client'}), 400

    elif data.get('ckv'):
        # ── C&KV submit-to-client ────────────────────────────────────────────
        # Finds the active concept_kv phase submission and marks it as sent.
        # concept_status must be internal_review — guards against double-submit.
        submission = ProjectSubmission.query.filter_by(
            project_id=project_id, is_active=True, phase='concept_kv'
        ).first()
        if not submission:
            return jsonify({'success': False, 'error': 'Upload a C&KV deck before submitting'}), 400
        if submission.is_flagged:
            return jsonify({'success': False, 'error': 'The current deck is flagged — wait for the designer to reupload'}), 400
        if project.concept_status != 'internal_review':
            return jsonify({'success': False, 'error': 'C&KV deck must be in Internal Review before submitting to client'}), 400

        # Stamp the submission as officially sent — file is now permanent
        submission.submitted_to_client_at = dt.utcnow()
        submission.submitted_by_id = current_user.id

        # Advance concept/KV statuses to submitted_to_client
        project.concept_status = 'submitted_to_client'
        if project.has_kv:
            project.kv_status = 'submitted_to_client'

        db.session.commit()

        # File is already on NAS from initial upload — nothing to do here
        log_activity('submitted_to_client',
                     f'C&KV for "{project.name}" submitted to client by {current_user.name}',
                     user=current_user, entity_type='project',
                     entity_name=project.name, entity_id=project.id)
        notify_of_submission_to_client(project, triggered_by=current_user)
        client_email = project.client_brand.contact_email if project.client_brand else None

        return jsonify({'success': True, 'client_email': client_email or '', 'project_name': project.name})

    else:
        submission = ProjectSubmission.query.filter_by(
            project_id=project_id, is_active=True
        ).first()
        if not submission:
            return jsonify({'success': False, 'error': 'Upload a client deck before submitting'}), 400
        if submission.is_flagged:
            return jsonify({'success': False, 'error': 'The current deck is flagged — wait for the designer to reupload'}), 400
        if project.project_status != 'internal_review':
            return jsonify({'success': False, 'error': 'Deck must be in Internal Review before submitting to client'}), 400

    # Stamp the submission as officially submitted — this file is now permanent
    submission.submitted_to_client_at = dt.utcnow()
    submission.submitted_by_id = current_user.id

    if channel:
        channel.status = 'submitted_to_client'
        is_revised_submission = False  # POSM channels track revisions via posm_revision_count
        # Push every included deliverable into submitted_to_client (POSM flow)
        for link in submission.included_deliverables:
            if link.deliverable:
                record_deliverable_status(link.deliverable, 'submitted_to_client', current_user)
    else:
        # NOTE: project.revision_count is NOT incremented here.
        # It is incremented only when CS sends a revision back (send_revision route).
        record_project_status(project, 'submitted_to_client', current_user)
        is_revised_submission = (project.revision_count or 0) > 0

        # Standard briefs only: mark included deliverables as submitted to client.
        # Only the deliverables selected in the submission picker are updated —
        # others (e.g. not yet ready) stay in their current state.
        # C&CM concept/KV submissions must not touch deliverables — they remain 'briefed'
        # until the POSM stage begins and the POSM channel flow takes over.
        if project.brief_type != 'ccm':
            included_ids = {link.deliverable_id for link in submission.included_deliverables if link.deliverable_id}
            for deliverable in project.project_deliverables:
                if deliverable.id in included_ids:
                    record_deliverable_status(deliverable, 'submitted_to_client', current_user)

            # Stamp revision_count on each *included* deliverable to match the current
            # client revision number. Using assignment (not +=) makes this idempotent:
            # if the same revision goes through multiple internal CS review cycles
            # (flag → reupload → re-submit internally → submit to client again), the
            # deliverable always ends up showing the correct revision number, not a
            # count of how many times CS hit "Submit to Client" on that revision.
            if is_revised_submission:
                for deliverable in project.project_deliverables:
                    if deliverable.id in included_ids:
                        deliverable.revision_count = project.revision_count

        # Advance concept/KV if they have an active status (i.e. were part of the workflow)
        if project.concept_status:
            project.concept_status = 'submitted_to_client'
        if project.kv_status:
            project.kv_status = 'submitted_to_client'

    db.session.commit()

    # File is already on NAS from initial upload — nothing to do here
    log_activity('submitted_to_client',
                 f'"{project.name}" submitted to client by {current_user.name}',
                 user=current_user, entity_type='project',
                 entity_name=project.name, entity_id=project.id)

    # Notify management, admin, and project designers
    notify_of_submission_to_client(project, triggered_by=current_user)

    # Return the client's email (dormant — will be populated once v1.1 adds client email UI)
    client_email = project.client_brand.contact_email if project.client_brand else None

    return jsonify({
        'success': True,
        'client_email': client_email or '',
        'project_name': project.name
    })


@submission_bp.route('/projects/submission/<int:submission_id>/download')
@login_required
def download_submission(submission_id):
    from app.models import ProjectSubmission
    from flask import send_file
    import io, os

    submission = ProjectSubmission.query.get_or_404(submission_id)
    project    = Project.query.get(submission.project_id)

    # All files live on NAS — upload route never saves to local disk
    from app.nas import download_app_file, build_file_path
    from flask import current_app
    nas_path   = build_file_path(project, 'Submissions', submission.original_filename)
    try:
        file_bytes = download_app_file(nas_path)
    except RuntimeError as e:
        current_app.logger.error(f'Submission download failed (id={submission_id}): {e}')
        return ('File could not be retrieved from storage. '
                'Please try again or contact support.', 502)
    return send_file(
        io.BytesIO(file_bytes),
        as_attachment=True,
        download_name=submission.original_filename
    )

def _load_submission_file_bytes(sub_file, project):
    """Return the raw bytes of a submission file, reading from wherever it
    physically lives right now.

    A Draft-stage file sits in the local draft cache
    (storage_location == 'cache' → bytes on disk at local_cache_path); every
    other file is on the NAS under the project's Submissions/ folder
    (storage_location == 'nas', the column default). Raises RuntimeError on
    any failure — deliberately the SAME contract app.nas.download_app_file
    already follows — so the two view functions below keep a single
    `except RuntimeError` branch and never have to care where the file was.
    """
    if sub_file.storage_location == 'cache':
        import os
        path = sub_file.local_cache_path
        if not path or not os.path.isfile(path):
            raise RuntimeError(
                f'cached submission file missing on disk '
                f'(file_id={sub_file.id}, path={path!r})'
            )
        with open(path, 'rb') as fh:
            return fh.read()

    # storage_location == 'nas' — read it off the NAS exactly as before.
    from app.nas import download_app_file, build_file_path
    nas_path = build_file_path(project, 'Submissions', sub_file.original_filename)
    return download_app_file(nas_path)


@submission_bp.route('/projects/submission/file/<int:file_id>/preview')
@login_required
def preview_submission_file(file_id):
    """Serve a supplementary submission file for inline browser preview.
    Same PDF/image-only restriction as reference file previews — these are
    arbitrary supplementary uploads, not always something a browser can
    render natively."""
    from app.models import ProjectSubmissionFile
    from flask import send_file, jsonify
    import io

    PREVIEWABLE_TYPES = {
        'pdf': 'application/pdf',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp',
    }

    extra = ProjectSubmissionFile.query.get_or_404(file_id)

    mimetype = PREVIEWABLE_TYPES.get((extra.file_type or '').lower())
    if not mimetype:
        return jsonify ({
            'success': False,
            'error': 'No preview available for this file type - download instead.'
            }), 415
    
    project = Project.query.get(extra.project_id)
    from flask import current_app
    try:
        file_bytes = _load_submission_file_bytes(extra, project)
    except RuntimeError as e:
        from flask import current_app
        current_app.logger.error(f'Submission file preview failed (file_id={file_id}): {e}')
        return jsonify({
            'success': False,
            'error': 'File could not be retrieved from storage. Try downloading it instead.'
        }), 502

    return send_file(
        io.BytesIO(file_bytes),
        mimetype=mimetype,
        as_attachment=False,
        download_name=extra.original_filename
    )

@submission_bp.route('/projects/<int:project_id>/submission/<int:submission_id>/add-file', methods=['POST'])
@login_required
@role_required('admin', 'designer', 'team_lead')
def add_submission_file(project_id, submission_id):
    """Attach an additional file to an existing active submission.

    Allows designers to upload multiple files against a single submission entry —
    e.g. both a PDF overview deck and individual artwork files. These extra files
    do not affect the submission state machine; they're purely supplementary."""
    import io

    project = Project.query.get_or_404(project_id)


    submission = ProjectSubmission.query.filter_by(
        id=submission_id, project_id=project_id, is_active=True
    ).first_or_404()

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    allowed = {'pdf', 'pptx', 'docx', 'doc', 'png', 'jpg', 'jpeg', 'zip'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed:
        return jsonify({'success': False, 'error': f'File type .{ext} is not supported'}), 400

    file_bytes = file.read()

    extra = ProjectSubmissionFile(
        submission_id=submission_id,
        project_id=project_id,
        original_filename=file.filename,
        file_type=ext,
        uploaded_by_id=current_user.id,
    )
    db.session.add(extra)
    db.session.commit()

    # Upload to NAS in background (same Submissions/ folder as the main deck)
    from app.nas import upload_app_file, build_file_path, _run_in_background
    _bg_folder      = build_file_path(project, 'Submissions', extra.original_filename).rsplit('/', 1)[0]
    _bg_bytes       = file_bytes
    _bg_filename    = extra.original_filename
    _bg_app         = current_app._get_current_object()
    _bg_uploader_id = current_user.id
    _bg_project_id  = project.id

    def _upload_extra_file():
        try:
            upload_app_file(_bg_bytes, _bg_folder, _bg_filename)
        except RuntimeError:
            from app.models import User as _U, Project as _P
            from app.notifications import create_notification
            uploader = _U.query.get(_bg_uploader_id)
            proj     = _P.query.get(_bg_project_id)
            if uploader and proj:
                create_notification(
                    recipient=uploader,
                    message=(f'Your file "{_bg_filename}" could not be saved to storage '
                             f'for "{proj.name}". Please try reuploading.'),
                    notification_type='nas_upload_failed',
                    project=proj,
                )

    _run_in_background(_bg_app, _upload_extra_file)

    log_activity('file_attached',
                 f'{current_user.name} added {file_type_label(ext)} as a supporting file to "{project.name}"',
                 user=current_user, entity_type='project',
                 entity_name=project.name, entity_id=project.id)

    return jsonify({
        'success': True,
        'file': {
            'id': extra.id,
            'original_filename': extra.original_filename,
            'file_type': extra.file_type,
            'uploaded_by': current_user.name,
        }
    })


@submission_bp.route('/projects/submission/file/<int:file_id>/download')
@login_required
def download_submission_file(file_id):
    """Download a supplementary file attached to a submission."""
    import io

    extra   = ProjectSubmissionFile.query.get_or_404(file_id)
    project = Project.query.get(extra.project_id)

    from flask import current_app
    try:
        file_bytes = _load_submission_file_bytes(extra, project)
    except RuntimeError as e:
        current_app.logger.error(f'Submission extra-file download failed (file_id={file_id}): {e}')
        return ('File could not be retrieved from storage. '
                'Please try again or contact support.', 502)
    return send_file(
        io.BytesIO(file_bytes),
        as_attachment=True,
        download_name=extra.original_filename
    )

@submission_bp.route('/projects/<int:project_id>/submissions/download-all')
@login_required
def download_all_submissions(project_id):
    """Zips every submission deck in this project's Submission History and
    returns a download link. Organizes the zip into subfolders matching how
    the history panel groups them on screen (Concept & KV / POSM by region)."""
    from app.zip_utils import build_zip
    from app.nas import download_app_file, build_file_path
    from app.models import ProjectSubmission

    project = Project.query.get_or_404(project_id)
    submissions = ProjectSubmission.query.filter(
        ProjectSubmission.project_id == project_id,
        ProjectSubmission.submitted_to_client_at.isnot(None)
    ).order_by(ProjectSubmission.submitted_to_client_at.desc()).all()

    if not submissions:
        return jsonify({'success': False, 'error': 'No submissions to download.'}), 400

    zip_files = []
    seen_names = {}
    for s in submissions:
        nas_path = build_file_path(project, 'Submissions', s.original_filename)
        try:
            content = download_app_file(nas_path)
        except RuntimeError:
            continue

        if s.phase == 'concept_kv':
            folder = 'Concept & KV'
        elif s.posm_customer:
            folder = f'POSM - {(s.posm_country or "Unknown").upper()} - {s.posm_customer.customer.name}'
        else:
            folder = f'POSM - {(s.posm_country or "Unknown").upper()}'

        name = s.original_filename
        key = f'{folder}/{name}'
        if key in seen_names:
            seen_names[key] += 1
            base, dot, ext = name.rpartition('.')
            name = f'{base} ({seen_names[key]}).{ext}' if dot else f'{name} ({seen_names[key]})'
        else:
            seen_names[key] = 0

        zip_files.append((f'{folder}/{name}', content))

    if not zip_files:
        return jsonify({'success': False, 'error': 'Could not fetch any files from the NAS.'}), 502

    zip_id = build_zip(zip_files, f'{project.name} - Submission History.zip')
    return jsonify({'success': True, 'download_url': url_for('api.zip_download', zip_id=zip_id)})


@submission_bp.route('/projects/submission/file/<int:file_id>', methods=['DELETE'])
@login_required
def delete_submission_file(file_id):
    """Delete a supplementary file. Only the uploader or an admin may delete."""
    extra   = ProjectSubmissionFile.query.get_or_404(file_id)
    project = Project.query.get(extra.project_id)

    if current_user.role != 'admin' and extra.uploaded_by_id != current_user.id:
        return jsonify({'success': False, 'error': 'Not authorised to delete this file'}), 403


    # Remove from NAS in background
    from app.nas import delete_app_file, build_file_path, _run_in_background
    _del_path = build_file_path(project, 'Submissions', extra.original_filename)
    _del_app  = current_app._get_current_object()
    _run_in_background(_del_app, lambda: delete_app_file(_del_path))

    db.session.delete(extra)
    db.session.commit()
    return jsonify({'success': True})


@submission_bp.route('/projects/<int:project_id>/submission/send-revision', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def send_revision(project_id):
    """CS sends a revision request back to the designer after the deck has been
    submitted to the client.
    - Requires project status to be submitted_to_client.
    - Records the free-text revision notes + which deliverables need rework.
    - Increments revision_count (this is the only place revision_count goes up).
    - Sets project → revision_in_queue; marked deliverables → revision_in_queue.
    - Deactivates the current active submission so the deck area appears empty.
    - Notifies all designers assigned to the project."""
    from app.models import ProjectSubmission, ProjectRevision, ProjectRevisionDeliverable
    from datetime import datetime as dt

    project = Project.query.get_or_404(project_id)


    data = request.get_json() or {}
    message = (data.get('message') or '').strip()
    deliverable_ids = data.get('deliverable_ids', [])
    includes_concept = bool(data.get('includes_concept', False))
    includes_kv = bool(data.get('includes_kv', False))
    posm_customer_id = data.get('posm_customer_id')
    posm_country     = (data.get('posm_country') or '').strip().lower() or None
    posm_channel_id  = data.get('posm_channel_id')

    if not message:
        return jsonify({'success': False, 'error': 'Please describe what needs to be revised'}), 400

    from app.utils import strip_html
    plain_message = strip_html(message)

    # Resolve channel (POSM parallel flow)
    channel = None
    if posm_channel_id:
        from app.models import ProjectPosmChannel
        channel = ProjectPosmChannel.query.filter_by(
            id=int(posm_channel_id), project_id=project_id
        ).first()

    # Status guard — channel or project level
    if channel:
        if channel.status != 'submitted_to_client':
            return jsonify({'success': False, 'error': 'Channel must be Submitted to Client before sending a revision'}), 400
    elif data.get('ckv'):
        # ── C&KV revision ────────────────────────────────────────────────────
        # Guard: C&KV must have been submitted to client before CS can send a revision.
        if project.concept_status != 'submitted_to_client':
            return jsonify({'success': False, 'error': 'C&KV must be Submitted to Client before sending a revision'}), 400

        # Create the revision record — no posm fields since this is the C&KV phase
        revision = ProjectRevision(
            project_id=project_id,
            message=message,
            sent_by_id=current_user.id,
            sent_at=dt.utcnow(),
            includes_concept=bool(project.has_concept),
            includes_kv=bool(project.has_kv),
            posm_customer_id=None,
            posm_country=None
        )
        db.session.add(revision)

        # Increment the C&KV-specific revision counter
        project.ckv_revision_count = (project.ckv_revision_count or 0) + 1

        # Move concept/KV statuses into revision_in_queue
        project.concept_status = 'revision_in_queue'
        if project.has_kv:
            project.kv_status = 'revision_in_queue'

        # Deactivate the C&KV submission so the deck area clears for reupload
        ckv_sub = ProjectSubmission.query.filter_by(
            project_id=project_id, is_active=True, phase='concept_kv'
        ).first()
        if ckv_sub:
            ckv_sub.is_active = False

        db.session.commit()

        # Notify C&KV designers
        concept_designer = project.concept_designer
        kv_designer = project.kv_designer
        notified = set()
        for designer in [concept_designer, kv_designer]:
            if designer and designer.id not in notified:
                notified.add(designer.id)
                create_notification(
                    recipient=designer,
                    message=f'C&KV revision #{project.ckv_revision_count} requested on "{project.name}" by {current_user.name}.',
                    notification_type='revision_requested',
                    project=project,
                    triggered_by=current_user
                )

        log_activity('revision_requested',
                     f'C&KV Revision #{project.ckv_revision_count} sent for "{project.name}" by {current_user.name}: {plain_message[:100]}',
                     user=current_user, entity_type='project',
                     entity_name=project.name, entity_id=project.id)
        return jsonify({'success': True})
    else:
        if project.project_status != 'submitted_to_client':
            return jsonify({'success': False, 'error': 'Project must be in Submitted to Client status to send a revision'}), 400
        if not deliverable_ids and not includes_concept and not includes_kv:
            return jsonify({'success': False, 'error': 'Select at least one item to revise'}), 400

    # Resolve POSM customer — channel takes precedence, else fall back to request fields
    posm_pc = None
    if channel and channel.posm_customer_id:
        from app.models import ProjectCustomer
        posm_pc = ProjectCustomer.query.get(channel.posm_customer_id)
    elif not channel and posm_customer_id:
        from app.models import ProjectCustomer
        posm_pc = ProjectCustomer.query.filter_by(
            id=int(posm_customer_id), project_id=project_id
        ).first()

    # Effective country — channel takes precedence
    effective_country = channel.posm_country if channel else posm_country

    # Create the revision record
    revision = ProjectRevision(
        project_id=project_id,
        message=message,
        sent_by_id=current_user.id,
        sent_at=dt.utcnow(),
        includes_concept=includes_concept,
        includes_kv=includes_kv,
        posm_customer_id=posm_pc.id if posm_pc else None,
        posm_country=effective_country
    )
    db.session.add(revision)
    db.session.flush()  # get revision.id before creating child rows

    if channel:
        # Channel POSM revision: update channel status and increment per-channel counter
        channel.status = 'revision_in_queue'

        # Deactivate only the channel's active submission
        ch_sub_q = ProjectSubmission.query.filter_by(
            project_id=project_id, is_active=True, posm_country=channel.posm_country
        )
        if channel.posm_customer_id is not None:
            ch_sub_q = ch_sub_q.filter(ProjectSubmission.posm_customer_id == channel.posm_customer_id)
        else:
            ch_sub_q = ch_sub_q.filter(ProjectSubmission.posm_customer_id == None)  # noqa: E711
        ch_active = ch_sub_q.first()

        # Link the channel's deliverables to this revision and move them to revision_in_queue.
        # We collect them from the active submission BEFORE deactivating it.
        if ch_active:
            for link in ch_active.included_deliverables:
                if link.deliverable_id:
                    db.session.add(ProjectRevisionDeliverable(
                        revision_id=revision.id,
                        deliverable_id=link.deliverable_id
                    ))
                    if link.deliverable:
                        record_deliverable_status(link.deliverable, 'revision_in_queue', current_user)
            ch_active.is_active = False

        # Increment per-channel revision counter
        if posm_pc:
            posm_pc.posm_revision_count = (posm_pc.posm_revision_count or 0) + 1
        elif effective_country and effective_country != 'uae':
            counts = dict(project.posm_country_revision_counts or {})
            counts[effective_country] = counts.get(effective_country, 0) + 1
            project.posm_country_revision_counts = counts

    else:
        # Link each selected deliverable to this revision and move it to revision_in_queue
        for d_id in deliverable_ids:
            deliverable = Deliverable.query.filter_by(id=d_id, project_id=project_id).first()
            if deliverable:
                db.session.add(ProjectRevisionDeliverable(
                    revision_id=revision.id,
                    deliverable_id=d_id
                ))
                record_deliverable_status(deliverable, 'revision_in_queue', current_user)

        # Move concept/KV into revision_in_queue if flagged
        if includes_concept:
            project.concept_status = 'revision_in_queue'
        if includes_kv:
            project.kv_status = 'revision_in_queue'

        # Increment global revision count — only place it moves
        project.revision_count = (project.revision_count or 0) + 1

        # UAE POSM: increment per-customer counter
        if posm_pc:
            posm_pc.posm_revision_count = (posm_pc.posm_revision_count or 0) + 1
        # Non-UAE Gulf POSM: increment per-country counter
        elif posm_country and posm_country != 'uae':
            counts = dict(project.posm_country_revision_counts or {})
            counts[posm_country] = counts.get(posm_country, 0) + 1
            project.posm_country_revision_counts = counts

        record_project_status(project, 'revision_in_queue', current_user)

        # Deactivate the current submission so the deck area appears empty (history is preserved)
        active_submission = ProjectSubmission.query.filter_by(
            project_id=project_id, is_active=True
        ).first()
        if active_submission:
            active_submission.is_active = False

    db.session.commit()

    # Build human-readable revision label for notifications/logs
    if channel:
        if channel.posm_country == 'uae' and posm_pc:
            ch_label = f'UAE — {posm_pc.customer.name}'
        else:
            ch_label = {'kuwait':'Kuwait','qatar':'Qatar','bahrain':'Bahrain','oman':'Oman'}.get(channel.posm_country, channel.posm_country.title())
        rev_label = f'POSM ({ch_label})'
    else:
        rev_label = f'#{project.revision_count}'

    # Notify every designer assigned to this project
    from app.models import ProjectDesigner
    assigned_designers = ProjectDesigner.query.filter_by(project_id=project_id).all()
    for assignment in assigned_designers:
        create_notification(
            recipient=assignment.designer,
            message=f'Revision {rev_label} requested on "{project.name}" by {current_user.name}.',
            notification_type='revision_requested',
            project=project,
            triggered_by=current_user
        )

    log_activity('revision_requested',
                 f'Revision {rev_label} sent for "{project.name}" by {current_user.name}: {plain_message[:100]}',
                 user=current_user, entity_type='project',
                 entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})


@submission_bp.route('/projects/<int:project_id>/submission/start-revision', methods=['POST'])
@login_required
@role_required('admin', 'designer', 'team_lead')
def start_revision(project_id):
    """Designer acknowledges the revision and starts work.
    - Requires project status to be revision_in_queue.
    - Sets the deliverables from the latest revision → revision_in_progress.
    - Sets project → revision_in_progress.
    - Notifies CS that work has begun."""
    from app.models import ProjectRevision

    project = Project.query.get_or_404(project_id)


    data = request.get_json(silent=True) or {}
    posm_channel_id = data.get('posm_channel_id')

    # Resolve channel (POSM parallel flow)
    channel = None
    if posm_channel_id:
        from app.models import ProjectPosmChannel
        channel = ProjectPosmChannel.query.filter_by(
            id=int(posm_channel_id), project_id=project_id
        ).first()

    if channel:
        if channel.status != 'revision_in_queue':
            return jsonify({'success': False, 'error': 'No revision is pending for this channel'}), 400
        channel.status = 'revision_in_progress'

        # Move the channel's revision deliverables into revision_in_progress
        revision = ProjectRevision.query.filter_by(
            project_id=project_id
        ).order_by(ProjectRevision.sent_at.desc()).first()
        if revision:
            for link in revision.revision_deliverables:
                if link.deliverable:
                    record_deliverable_status(link.deliverable, 'revision_in_progress', current_user)
    elif data.get('ckv'):
        # ── C&KV start revision ───────────────────────────────────────────────
        # Designer acknowledges the C&KV revision and starts working on it.
        if project.concept_status != 'revision_in_queue':
            return jsonify({'success': False, 'error': 'No C&KV revision is pending'}), 400

        # Advance concept/KV into in-progress so the template shows the upload button
        project.concept_status = 'revision_in_progress'
        if project.has_kv:
            project.kv_status = 'revision_in_progress'

        db.session.commit()

        # Notify CS lead that the designer has started
        if project.cs_lead and project.cs_lead.id != current_user.id:
            create_notification(
                recipient=project.cs_lead,
                message=f'{current_user.name} has started C&KV Revision #{project.ckv_revision_count} on "{project.name}"',
                notification_type='revision_started',
                project=project,
                triggered_by=current_user
            )

        log_activity('revision_started',
                     f'C&KV Revision #{project.ckv_revision_count} started on "{project.name}" by {current_user.name}',
                     user=current_user, entity_type='project',
                     entity_name=project.name, entity_id=project.id)
        return jsonify({'success': True})
    else:
        if project.project_status != 'revision_in_queue':
            return jsonify({'success': False, 'error': 'No revision is pending for this project'}), 400

        revision = ProjectRevision.query.filter_by(
            project_id=project_id
        ).order_by(ProjectRevision.sent_at.desc()).first()

        if not revision:
            return jsonify({'success': False, 'error': 'No revision record found'}), 400

        for link in revision.revision_deliverables:
            if link.deliverable:
                record_deliverable_status(link.deliverable, 'revision_in_progress', current_user)

        record_project_status(project, 'revision_in_progress', current_user)

    db.session.commit()

    rev_label = f'#{project.revision_count}' if not channel else 'POSM'

    if project.cs_lead and project.cs_lead.id != current_user.id:
        create_notification(
            recipient=project.cs_lead,
            message=(f'{current_user.name} has started Revision {rev_label} '
                     f'on "{project.name}"'),
            notification_type='revision_started',
            project=project,
            triggered_by=current_user
        )

    log_activity('revision_started',
                 f'Revision {rev_label} started on "{project.name}" by {current_user.name}',
                 user=current_user, entity_type='project',
                 entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})

# -------- Convert PDF to PPTX for file preview -----#

@submission_bp.route('/projects/submission/<int:submission_id>/preview')
@login_required
def preview_submission(submission_id):
    """Serve a submission deck for inline browser preview instead of download.
    PDFs are streamed as-is. PPTX decks get converted to PDF on the fly first,
    since browsers can't render PowerPoint natively — this way the frontend
    only ever has to deal with one format regardless of what was uploaded."""
    from app.models import ProjectSubmission
    from app.nas import download_app_file, build_file_path
    from app.pptx_convert import convert_pptx_to_pdf
    from flask import send_file, jsonify, current_app
    import io, subprocess

    submission = ProjectSubmission.query.get_or_404(submission_id)
    project    = Project.query.get(submission.project_id)

    nas_path   = build_file_path(project, 'Submissions', submission.original_filename)
    try:
        file_bytes = download_app_file(nas_path)
    except RuntimeError as e:
        current_app.logger.error(f'Submission preview NAS fetch failed (id={submission_id}): {e}')
        return jsonify({
            'success': False,
            'error': 'File could not be retrieved from storage. Try downloading instead.'
        }), 502

    if submission.file_type.lower() == 'pptx':
        try:
            file_bytes = convert_pptx_to_pdf(file_bytes)
        except (subprocess.TimeoutExpired, RuntimeError) as e:
            current_app.logger.warning(
                f'Preview conversion failed for submission {submission_id}: {e}'
            )
            return jsonify({
                'success': False,
                'error': 'Preview unavailable for this file — try downloading instead.'
            }), 502

    return send_file(
        io.BytesIO(file_bytes),
        mimetype='application/pdf',
        as_attachment=False,
        download_name=submission.original_filename.rsplit('.', 1)[0] + '.pdf'
    )
