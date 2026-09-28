"""
project_overlay/submissions.py — the overlay's Submissions page: the draft-card
read view, file upload/manage, submit-for-review / submit-to-client /
client-revision / approve flows, and internal-revision flagging.
"""

from flask import render_template, request, jsonify
from flask_login import login_required

from app.modules.core.shared.models import Project

from ._common import (project_overlay_bp, _get_actor, ensure_posm_channels,
                      submissions_blocked_reason)
from app.modules.core.shared.lib.capabilities import can

def _build_submission_regions(project):
    """Group a C&CM project's active customers as Region -> Customer for the
    Submissions scope picker. Customers only; submission data is fetched per
    selection. A light version of _build_ccm_deliverable_sections.
    """
    region_names = {
        'uae': 'UAE', 'kuwait': 'Kuwait', 'qatar': 'Qatar',
        'bahrain': 'Bahrain', 'oman': 'Oman', 'other': 'Other',
    }
    region_order = ['uae', 'kuwait', 'qatar', 'bahrain', 'oman', 'other']

    by_region = {}
    for pc in project.project_customers:
        if pc.cancelled:
            continue
        # Only region_order is rendered, so an unlisted region folds into
        # 'other' rather than hiding the customer.
        region_key = pc.customer.region if pc.customer.region in region_names else 'other'
        by_region.setdefault(region_key, []).append(pc)

    sections = []
    for region_key in region_order:
        if region_key not in by_region:
            continue
        sections.append({
            'key': region_key,
            'name': region_names.get(region_key, region_key.title()),
            'customers': by_region[region_key],
        })
    return sections

def _resolve_submission_scope(project, scope, customer_id=None):
    """
    Turn a Submissions selection (scope='ckv', or scope='customer' +
    customer_id) into the phase/channel a ProjectSubmission is keyed by.
    Every Submissions route uses this so scoping stays consistent.

    Returns {'channel': ProjectPosmChannel|None, 'phase': str,
    'posm_country': str|None, 'posm_customer_id': int|None}.
    """
    from app.modules.core.shared.models import ProjectPosmChannel

    if scope == 'customer' and customer_id:
        channel = ProjectPosmChannel.query.filter_by(
            project_id=project.id, posm_customer_id=customer_id
        ).first()
        return {
            'channel': channel,
            'phase': 'posm',
            'posm_country': channel.posm_country if channel else None,
            'posm_customer_id': customer_id,
        }

    # scope == 'ckv', or a Standard project (no scope at all): both use the
    # non-channel 'concept_kv' phase.
    return {'channel': None, 'phase': 'concept_kv', 'posm_country': None, 'posm_customer_id': None}


def _get_active_draft(project, resolved):
    """The active pre-client ProjectSubmission for this scope: draft,
    internal_review, or internal_revision (locked or flagged still counts).
    Rows with workflow_status NULL are excluded."""
    from app.modules.core.shared.models import ProjectSubmission
    return ProjectSubmission.query.filter_by(
        project_id=project.id,
        phase=resolved['phase'],
        posm_country=resolved['posm_country'],
        posm_customer_id=resolved['posm_customer_id'],
        is_active=True,
    ).filter(
        ProjectSubmission.workflow_status.in_(['draft', 'internal_review', 'internal_revision'])
    ).first()

def _get_sent_submission(project, resolved):
    """The most recent active submission for this scope with
    workflow_status='sent_to_client', shown read-only beside the draft."""
    from app.modules.core.shared.models import ProjectSubmission
    return ProjectSubmission.query.filter_by(
        project_id=project.id,
        phase=resolved['phase'],
        posm_country=resolved['posm_country'],
        posm_customer_id=resolved['posm_customer_id'],
        is_active=True,
        workflow_status='sent_to_client',
    ).order_by(ProjectSubmission.submitted_to_client_at.desc()).first()

def _get_submission_history(project, resolved):
    """Every submission for this scope ever sent to the client, newest first,
    including the current one. Not filtered by is_active, so past revisions
    still appear."""
    from app.modules.core.shared.models import ProjectSubmission
    return ProjectSubmission.query.filter_by(
        project_id=project.id,
        phase=resolved['phase'],
        posm_country=resolved['posm_country'],
        posm_customer_id=resolved['posm_customer_id'],
    ).filter(
        ProjectSubmission.submitted_to_client_at.isnot(None)
    ).order_by(ProjectSubmission.submitted_to_client_at.desc()).all()


def _revision_label_from_name(name):
    """Pull the 'Initial' / 'Revision N' label out of a canonical deck name for
    a compact history chip; falls back to the bare filename."""
    import re
    m = re.search(r'-\s*(Initial|Revision\s+\d+)\.[^.]+$', name or '', re.IGNORECASE)
    return m.group(1) if m else (name or 'Deck')

def _build_draft_card_context(project, actor, resolved):
    """Template context for the Draft card of one Submissions scope (Standard
    page render and C&CM per-scope fetch).

    Editability: draft and internal_revision are editable; internal_review is
    locked unless is_being_edited (a designer clicked Edit). Submit for Review
    re-locks and clears is_being_edited.
    """
    from app.modules.core.shared.models import ProjectSubmissionFile, Deliverable, ProjectSubmissionDeliverable
    from sqlalchemy.orm import joinedload

    draft = _get_active_draft(project, resolved)
    cached_files = []
    if draft:
        cached_files = ProjectSubmissionFile.query.filter_by(
            submission_id=draft.id, storage_location='cache'
        ).order_by(
            ProjectSubmissionFile.is_main_deck.desc(),
            ProjectSubmissionFile.uploaded_at.asc(),
        ).all()

    workflow_status = draft.workflow_status if draft else 'draft'
    is_being_edited = bool(draft.is_being_edited) if draft else False
    is_editable = (
        workflow_status in ('draft', 'internal_revision')
        or (workflow_status == 'internal_review' and is_being_edited)
    )
    is_locked = draft is not None and not is_editable

    events = list(draft.events) if draft else []

    # Always fetched, even with an active draft: the card shows the deck that
    # is with the client above the working draft.
    sent_submission = _get_sent_submission(project, resolved)
    sent_files = []
    if sent_submission:
        sent_files = ProjectSubmissionFile.query.filter_by(
            submission_id=sent_submission.id
        ).order_by(
            ProjectSubmissionFile.is_main_deck.desc(),
            ProjectSubmissionFile.uploaded_at.asc(),
        ).all()

    # A client revision can be requested once per sent deck; after that the
    # card shows the client's message (the client_revision event).
    sent_revision_event = None
    if sent_submission:
        sent_revision_event = next(
            (e for e in sent_submission.events if e.event_type == 'client_revision'), None)
    can_request_client_revision = (
        can('review_submissions', actor)
        and sent_submission is not None
        and sent_revision_event is None
    )

    history = _get_submission_history(project, resolved)
    history_ids = [sub.id for sub in history]

    # Two batch queries for all revisions' files and deliverable links. The
    # global sort keeps each submission's file order after grouping.
    files_by_submission = {}
    if history_ids:
        all_files = ProjectSubmissionFile.query.filter(
            ProjectSubmissionFile.submission_id.in_(history_ids)
        ).order_by(
            ProjectSubmissionFile.is_main_deck.desc(),
            ProjectSubmissionFile.uploaded_at.asc(),
        ).all()
        for f in all_files:
            files_by_submission.setdefault(f.submission_id, []).append(f)

    links_by_submission = {}
    if history_ids:
        all_links = ProjectSubmissionDeliverable.query.options(
            joinedload(ProjectSubmissionDeliverable.deliverable)
        ).filter(
            ProjectSubmissionDeliverable.submission_id.in_(history_ids)
        ).all()
        for link in all_links:
            links_by_submission.setdefault(link.submission_id, []).append(link)

    history_submissions = []
    for sub in history:
        sub_links = links_by_submission.get(sub.id, [])
        history_submissions.append({
            'submission': sub,
            'files': files_by_submission.get(sub.id, []),
            'label': _revision_label_from_name(sub.original_filename),
            'included_names': [link.deliverable.name for link in sub_links if link.deliverable],
            'includes_concept': sub.includes_concept,
            'includes_kv': sub.includes_kv,
        })



    

    # Picker options. C&CM's Concept & KV scope uses concept/KV toggles, not
    # deliverables. A Standard project is also phase='concept_kv' but picks
    # from its real deliverables.
    is_ckv_toggle_scope = resolved['phase'] == 'concept_kv' and project.brief_type == 'ccm'
    if is_ckv_toggle_scope:
        deliverable_options = []
    elif resolved['phase'] == 'concept_kv':
        deliverable_options = Deliverable.query.filter_by(
            project_id=project.id, project_customer_id=None
        ).order_by(Deliverable.id).all()
    else:
        deliverable_options = Deliverable.query.filter_by(
            project_id=project.id, project_customer_id=resolved['posm_customer_id']
        ).order_by(Deliverable.id).all()

    selected_deliverable_ids = []
    includes_concept = False
    includes_kv = False
    if draft:
        selected_deliverable_ids = [link.deliverable_id for link in draft.included_deliverables]
        includes_concept = draft.includes_concept
        includes_kv = draft.includes_kv

    # Client Approval has the same gate as Client Revision. Approval is per
    # deliverable, so only not-yet-approved ones are offered. C&CM Concept &
    # KV is approved as a pair, so it has no picker.
    can_mark_approved = can_request_client_revision
    approvable_deliverables = []
    if can_mark_approved and sent_submission and not is_ckv_toggle_scope:
        from app.modules.core.shared.lib.status_vocabulary import derive_deliverable_status
        approvable_deliverables = [
            {'deliverable': link.deliverable, 'pill': derive_deliverable_status(link.deliverable)}
            for link in sent_submission.included_deliverables
            if link.deliverable and link.deliverable.status != 'approved'
        ]

    if is_ckv_toggle_scope:
        all_deliverables_approved = (
            (not project.has_concept or project.concept_status == 'approved')
            and (not project.has_kv or project.kv_status == 'approved')
        )
    else:
        all_deliverables_approved = bool(deliverable_options) and all(
            d.status == 'approved' for d in deliverable_options
        )

    revisable_deliverables = []
    if can_request_client_revision and sent_submission and not is_ckv_toggle_scope:
        from app.modules.core.shared.lib.status_vocabulary import derive_deliverable_status
        revisable_deliverables = [
            {'deliverable': link.deliverable, 'pill': derive_deliverable_status(link.deliverable)}
            for link in sent_submission.included_deliverables
            if link.deliverable
        ]

    # Same check the write routes use, so the card never offers what the
    # server will refuse.
    submissions_open = submissions_blocked_reason(project) is None

    return {
        'draft': draft,
        'cached_files': cached_files,
        'can_manage_draft': can('manage_drafts', actor) and submissions_open,
        'submissions_open': submissions_open,
        'can_review': can('review_submissions', actor),
        'workflow_status': workflow_status,
        'is_being_edited': is_being_edited,
        'is_locked': is_locked,
        'events': events,
        'is_ckv_toggle_scope': is_ckv_toggle_scope,
        'deliverable_options': deliverable_options,
        'selected_deliverable_ids': selected_deliverable_ids,
        'includes_concept': includes_concept,
        'includes_kv': includes_kv,
        'has_concept': project.has_concept,
        'has_kv': project.has_kv,
        'sent_submission': sent_submission,
        'sent_revision_event': sent_revision_event,
        'can_request_client_revision': can_request_client_revision,
        'can_mark_approved': can_mark_approved,
        'all_deliverables_approved': all_deliverables_approved,
        'approvable_deliverables': approvable_deliverables,
        'revisable_deliverables': revisable_deliverables,
        'sent_files': sent_files,
        'history_submissions': history_submissions,
    }


@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions')
@login_required
def overlay_submissions(project_id):
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    if project.brief_type != 'ccm':
        resolved = _resolve_submission_scope(project, 'ckv')
        draft_context = _build_draft_card_context(project, actor, resolved)
        return render_template(
            'project_overlay/_submissions_standard.html',
            project=project, scope='ckv', customer_id=None,
            **draft_context
        )

    regions = _build_submission_regions(project)
    brief_sections = {r['key']: r['customers'] for r in regions}
    ensure_posm_channels(project, brief_sections)

    has_gulf_regions = any(r['key'] in ('kuwait', 'qatar', 'bahrain', 'oman') for r in regions)
    all_customers = [c for r in regions for c in r['customers']]
    show_ckv = bool(project.has_concept or project.has_kv)

    return render_template(
        'project_overlay/_submissions_ccm.html',
        project=project,
        regions=regions,
        has_gulf_regions=has_gulf_regions,
        default_region_key=regions[0]['key'] if regions else None,
        default_customer_id=all_customers[0].id if all_customers else None,
        show_ckv=show_ckv,
        # False when there are no customers and no Concept/KV; the template
        # then shows an empty state.
        has_any_scope=bool(show_ckv or all_customers),
    )


@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/content')
@login_required
def overlay_submissions_content(project_id):
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    scope = request.args.get('scope', 'ckv')
    customer_id = request.args.get('customer_id', type=int)

    resolved = _resolve_submission_scope(project, scope, customer_id)
    draft_context = _build_draft_card_context(project, actor, resolved)

    return render_template(
        'project_overlay/_submissions_draft_card.html',
        project=project, scope=scope, customer_id=customer_id,
        **draft_context
    )

@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/draft/upload', methods=['POST'])
@login_required
def overlay_submissions_upload(project_id):
    """
    Add a file to the scope's draft in the local cache, not the NAS (see
    app/modules/projects/lib/submission_cache.py). Creates the draft on the
    first file, with 'draft' placeholder names until Submit to Client names
    the zip. The first file in a new draft becomes is_main_deck.
    """
    from app.modules.core.shared.models import ProjectSubmission, ProjectSubmissionFile
    from app.modules.projects.lib.submission_cache import cache_submission_file
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity
    from flask import jsonify

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not can('manage_drafts', actor):
        return jsonify({'success': False, 'error': 'You do not have permission to change this draft.'}), 403
    blocked = submissions_blocked_reason(project)
    if blocked:
        return jsonify({'success': False, 'error': blocked}), 409

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    allowed = {'pdf', 'pptx', 'docx', 'doc', 'png', 'jpg', 'jpeg', 'ai', 'psd', 'zip'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed:
        return jsonify({'success': False, 'error': f'File type .{ext} is not supported'}), 400

    scope = request.form.get('scope', 'ckv')
    customer_id = request.form.get('customer_id', type=int)
    resolved = _resolve_submission_scope(project, scope, customer_id)

    draft = _get_active_draft(project, resolved)
    if not draft:
        # Guard for "one active draft per scope". Never deactivates the sent
        # deck, which stays active beside the new draft. This is the same
        # filter _get_active_draft just ran, so it always finds nothing.
        previous = ProjectSubmission.query.filter_by(
            project_id=project.id,
            phase=resolved['phase'],
            posm_country=resolved['posm_country'],
            posm_customer_id=resolved['posm_customer_id'],
            is_active=True,
        ).filter(
            ProjectSubmission.workflow_status.in_(['draft', 'internal_review', 'internal_revision'])
        ).first()
        if previous:
            previous.is_active = False

        draft = ProjectSubmission(
            project_id=project.id,
            filename='draft',
            original_filename='draft',
            file_type='draft',
            uploaded_by_id=actor.id,
            is_active=True,
            phase=resolved['phase'],
            posm_country=resolved['posm_country'],
            posm_customer_id=resolved['posm_customer_id'],
            workflow_status='draft',
        )
        db.session.add(draft)
        db.session.flush() # need draft.id before caching the file under it

    file_bytes = file.read()
    local_path = cache_submission_file(project.id, draft.id, file_bytes, file.filename)

    existing_count = ProjectSubmissionFile.query.filter_by(
        submission_id=draft.id, storage_location='cache'
    ).count()

    draft_file = ProjectSubmissionFile(
        submission_id=draft.id,
        project_id=project.id,
        original_filename=file.filename,
        file_type=ext,
        uploaded_by_id=actor.id,
        storage_location='cache',
        local_cache_path=local_path,
        is_main_deck=(existing_count == 0),
    )
    db.session.add(draft_file)
    db.session.commit()

    log_activity('submission_draft_file_added',
                 f'{actor.name} added "{file.filename}" to the draft submission for "{project.name}"',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({
        'success': True,
        'submission_id': draft.id,
        'file': {
            'id': draft_file.id,
            'original_filename': draft_file.original_filename,
            'file_type': draft_file.file_type,
            'is_main_deck': draft_file.is_main_deck,
            'uploaded_by': actor.name,
        }
    })

@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/draft/file/<int:file_id>/remove', methods=['POST'])
@login_required
def overlay_submissions_remove_draft_file(project_id, file_id):
    """
    Remove one file from a draft's local cache.

    Removing the main deck while other files remain needs a replacement in
    the same request: 'new_main_deck_file_id' (promote a sibling) or 'file'
    (upload a new main deck). With neither, nothing is deleted and a 409
    lists the other files so the UI can ask. A lone main deck deletes freely.
    """
    from app.modules.core.shared.models import ProjectSubmissionFile
    from app.modules.projects.lib.submission_cache import cache_submission_file, delete_cached_file
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity
    from flask import jsonify

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not can('manage_drafts', actor):
        return jsonify({'success': False, 'error': 'You do not have permission to change this draft.'}), 403
    blocked = submissions_blocked_reason(project)
    if blocked:
        return jsonify({'success': False, 'error': blocked}), 409

    target = ProjectSubmissionFile.query.filter_by(
        id=file_id, project_id=project.id, storage_location='cache'
    ).first_or_404()

    submission_id = target.submission_id
    siblings = ProjectSubmissionFile.query.filter(
        ProjectSubmissionFile.submission_id == submission_id,
        ProjectSubmissionFile.storage_location == 'cache',
        ProjectSubmissionFile.id != target.id,
    ).all()

    if target.is_main_deck and siblings:
        new_main_deck_file_id = request.form.get('new_main_deck_file_id', type=int)
        new_file = request.files.get('file')

        if not new_main_deck_file_id and not new_file:
            return jsonify({
                'success': False,
                'error': 'main_deck_replacement_required',
                'other_files': [
                    {'id': f.id, 'original_filename': f.original_filename}
                    for f in siblings
                ],
            }), 409

        if new_main_deck_file_id:
            promoted = next((f for f in siblings if f.id == new_main_deck_file_id), None)
            if not promoted:
                return jsonify({'success': False, 'error': 'new_main_deck_file_id not found in this draft'}), 400
            promoted.is_main_deck = True
        else:
            allowed = {'pdf', 'pptx', 'docx', 'doc', 'png', 'jpg', 'jpeg', 'ai', 'psd', 'zip'}
            ext = new_file.filename.rsplit('.', 1)[-1].lower() if '.' in new_file.filename else ''
            if ext not in allowed:
                return jsonify({'success': False, 'error': f'File type .{ext} is not supported'}), 400
            file_bytes = new_file.read()
            local_path = cache_submission_file(project.id, submission_id, file_bytes, new_file.filename)
            promoted = ProjectSubmissionFile(
                submission_id=submission_id,
                project_id=project.id,
                original_filename=new_file.filename,
                file_type=ext,
                uploaded_by_id=actor.id,
                storage_location='cache',
                local_cache_path=local_path,
                is_main_deck=True,
            )
            db.session.add(promoted)

    removed_name = target.original_filename
    delete_cached_file(target.local_cache_path)
    db.session.delete(target)
    db.session.commit()

    log_activity('submission_draft_file_removed',
                 f'{actor.name} removed "{removed_name}" from the draft submission for "{project.name}"',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})

@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/draft/file/<int:file_id>/set-main-deck', methods=['POST'])
@login_required
def overlay_submissions_set_main_deck(project_id, file_id):
    """
    "Set as Main Deck": promote a cached file and demote the current main
    deck (at most one holds the flag).
    """
    from app.modules.core.shared.models import ProjectSubmissionFile
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity
    from flask import jsonify

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not can('manage_drafts', actor):
        return jsonify({'success': False, 'error': 'You do not have permission to change this draft.'}), 403
    blocked = submissions_blocked_reason(project)
    if blocked:
        return jsonify({'success': False, 'error': blocked}), 409

    target = ProjectSubmissionFile.query.filter_by(
        id=file_id, project_id=project.id, storage_location='cache'
    ).first_or_404()

    if not target.is_main_deck:
        current_main = ProjectSubmissionFile.query.filter_by(
            submission_id=target.submission_id, storage_location='cache', is_main_deck=True
        ).first()
        if current_main:
            current_main.is_main_deck = False
        target.is_main_deck = True
        db.session.commit()

        log_activity('submission_draft_main_deck_changed',
                     f'{actor.name} set "{target.original_filename}" as the main deck for the draft submission on "{project.name}"',
                     user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})

@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/draft/submit-for-review', methods=['POST'])
@login_required
def overlay_submissions_submit_for_review(project_id):
    """
    Lock the draft and send it to CS for internal review: first submission
    and every re-submission after an Edit or Internal Revision. Records the
    included deliverables (ProjectSubmissionDeliverable) or Concept/KV.

    Body (JSON): scope, customer_id, note (optional), deliverable_ids
    (Standard / C&CM customer scope) or includes_concept / includes_kv
    (C&CM Concept & KV scope only).
    """
    from app.modules.core.shared.models import (Deliverable, ProjectSubmissionDeliverable,
                             ProjectSubmissionEvent, ProjectSubmissionFile)
    from app.modules.core.shared.services.status_tracking import record_deliverable_status
    from app.modules.core.shared.services.notifications import create_notification
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.extensions import db
    from flask import jsonify

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not can('manage_drafts', actor):
        return jsonify({'success': False, 'error': 'You do not have permission to submit this draft.'}), 403

    blocked = submissions_blocked_reason(project)
    if blocked:
        return jsonify({'success': False, 'error': blocked}), 409

    data = request.get_json() or {}
    scope = data.get('scope', 'ckv')
    customer_id = data.get('customer_id')
    note = (data.get('note') or '').strip() or None
    deliverable_ids = data.get('deliverable_ids') or []
    includes_concept = bool(data.get('includes_concept', False))
    includes_kv = bool(data.get('includes_kv', False))

    resolved = _resolve_submission_scope(project, scope, customer_id)
    draft = _get_active_draft(project, resolved)
    if not draft:
        return jsonify({'success': False, 'error': 'No active draft to submit.'}), 400

    has_files = ProjectSubmissionFile.query.filter_by(
        submission_id=draft.id, storage_location='cache'
    ).first() is not None
    if not has_files:
        return jsonify({'success': False, 'error': 'Add at least one file before submitting.'}), 400

    is_ckv_toggle_scope = resolved['phase'] == 'concept_kv' and project.brief_type == 'ccm'
    if is_ckv_toggle_scope:
        if not includes_concept and not includes_kv:
            return jsonify({'success': False, 'error': 'Select Concept and/or KV to include.'}), 400
    elif not deliverable_ids:
        return jsonify({'success': False, 'error': 'Select at least one deliverable to include.'}), 400

    # Replace the deliverable links wholesale.
    ProjectSubmissionDeliverable.query.filter_by(submission_id=draft.id).delete()
    for d_id in deliverable_ids:
        deliverable = Deliverable.query.filter_by(id=d_id, project_id=project.id).first()
        if deliverable:
            db.session.add(ProjectSubmissionDeliverable(submission_id=draft.id, deliverable_id=d_id))
            record_deliverable_status(deliverable, 'internal_review', actor)

    draft.includes_concept = includes_concept
    draft.includes_kv = includes_kv
    if is_ckv_toggle_scope:
        if includes_concept and project.has_concept:
            project.concept_status = 'internal_review'
        if includes_kv and project.has_kv:
            project.kv_status = 'internal_review'

    was_reopened = draft.workflow_status in ('internal_review', 'internal_revision')
    draft.workflow_status = 'internal_review'
    draft.is_being_edited = False
    draft.editing_started_at = None

    db.session.add(ProjectSubmissionEvent(
        submission_id=draft.id, event_type='submitted_for_review',
        author_id=actor.id, message=note,
    ))

    db.session.commit()

    if project.cs_lead and project.cs_lead.id != actor.id:
        create_notification(
            recipient=project.cs_lead,
            message=(f'"{project.name}" was updated and re-submitted for internal review by {actor.name}'
                      if was_reopened else
                      f'"{project.name}" has been submitted for internal review by {actor.name}'),
            notification_type='internal_review_submitted',
            project=project,
            triggered_by=actor,
        )

    log_activity('internal_review_submitted',
                 f'"{project.name}" submitted for internal review by {actor.name} '
                 f'({len(deliverable_ids)} deliverable(s) included)',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/draft/edit', methods=['POST'])
@login_required
def overlay_submissions_edit_draft(project_id):
    """
    Designer reopens a submission locked in internal_review, with a required
    reason logged as an 'edited' event. workflow_status stays internal_review;
    is_being_edited is what unlocks the card. (internal_revision is already
    editable, so it needs no such route.)
    """
    from app.modules.core.shared.models import ProjectSubmissionEvent
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.extensions import db
    from datetime import datetime as dt
    from flask import jsonify

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not can('manage_drafts', actor):
        return jsonify({'success': False, 'error': 'You do not have permission to edit this draft.'}), 403

    blocked = submissions_blocked_reason(project)
    if blocked:
        return jsonify({'success': False, 'error': blocked}), 409

    data = request.get_json() or {}
    scope = data.get('scope', 'ckv')
    customer_id = data.get('customer_id')
    reason = (data.get('reason') or '').strip()
    if not reason:
        return jsonify({'success': False, 'error': 'Please provide a reason for editing.'}), 400

    resolved = _resolve_submission_scope(project, scope, customer_id)
    draft = _get_active_draft(project, resolved)
    if not draft or draft.workflow_status != 'internal_review':
        return jsonify({'success': False, 'error': 'This draft is not currently locked for review.'}), 400

    draft.is_being_edited = True
    draft.editing_started_at = dt.utcnow()

    db.session.add(ProjectSubmissionEvent(
        submission_id=draft.id, event_type='edited',
        author_id=actor.id, message=reason,
    ))
    db.session.commit()

    log_activity('submission_draft_edit_started',
                 f'{actor.name} reopened the locked draft submission on "{project.name}" to fix: {reason}',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/draft/flag-internal-revision', methods=['POST'])
@login_required
def overlay_submissions_flag_internal_revision(project_id):
    """
    CS flags a submission in internal_review with a revision note (rich HTML,
    may hold inline images from rich-editor.js). Sets internal_revision, which
    is editable straight away, and moves the included deliverables and
    Concept/KV to internal_revision too.
    """
    from app.modules.core.shared.models import ProjectSubmissionEvent
    from app.modules.core.shared.services.status_tracking import record_deliverable_status
    from app.modules.core.shared.services.notifications import create_notification
    from app.modules.core.shared.lib.utils import strip_html, log_activity
    from app.modules.core.shared.extensions import db
    from flask import jsonify

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not can('review_submissions', actor):
        return jsonify({'success': False, 'error': 'You do not have permission to flag this submission.'}), 403

    blocked = submissions_blocked_reason(project)
    if blocked:
        return jsonify({'success': False, 'error': blocked}), 409

    data = request.get_json() or {}
    scope = data.get('scope', 'ckv')
    customer_id = data.get('customer_id')
    message = (data.get('message') or '').strip()
    if not message or not strip_html(message).strip():
        return jsonify({'success': False, 'error': 'Please provide a reason for the revision.'}), 400

    resolved = _resolve_submission_scope(project, scope, customer_id)
    draft = _get_active_draft(project, resolved)
    if not draft or draft.workflow_status != 'internal_review':
        return jsonify({'success': False, 'error': 'This submission is not currently pending review.'}), 400

    draft.workflow_status = 'internal_revision'
    draft.is_being_edited = False
    draft.editing_started_at = None

    for link in draft.included_deliverables:
        if link.deliverable:
            record_deliverable_status(link.deliverable, 'internal_revision', actor)
    if draft.includes_concept and project.has_concept:
        project.concept_status = 'internal_revision'
    if draft.includes_kv and project.has_kv:
        project.kv_status = 'internal_revision'

    db.session.add(ProjectSubmissionEvent(
        submission_id=draft.id, event_type='internal_revision',
        author_id=actor.id, message=message,
    ))
    db.session.commit()

    plain_message = strip_html(message)
    if draft.uploaded_by and draft.uploaded_by.id != actor.id:
        create_notification(
            recipient=draft.uploaded_by,
            message=f'Your submission for "{project.name}" was flagged for internal revision by {actor.name}: {plain_message}',
            notification_type='internal_revision_flagged',
            project=project,
            triggered_by=actor,
        )

    log_activity('internal_revision_flagged',
                 f'Draft submission for "{project.name}" flagged for internal revision by {actor.name}: {plain_message}',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})

def _canonical_deck_basename(project, resolved):
    """Canonical deck name without extension, used for the NAS zip and its
    main-deck member. By scope:
      - POSM channel, per-customer: "<Client> - <Project> - <Country> - <Customer> - POSM - <Initial|Revision N>"
      - POSM channel, per-country (legacy, posm_customer_id NULL): "... - <Country> - POSM - <label>"
      - POSM channel, no country: "... - POSM - <label>" (project.revision_count)
      - C&CM Concept & KV: "<Client> - <Project> - Concept & KV - <Initial|Revision N>" (project.ckv_revision_count)
      - Standard Brief: "<Client> - <Project> - <Initial|Revision N>" (project.revision_count)
    Reads the current revision counters; only the Client Revision flow bumps them."""
    import re

    def _sanitize(s):
        return re.sub(r'[\\/:*?"<>|]', '', s or '').strip()

    GULF_REGION_NAMES = {'uae': 'UAE', 'kuwait': 'Kuwait', 'qatar': 'Qatar',
                         'bahrain': 'Bahrain', 'oman': 'Oman'}
    client = _sanitize(project.client_brand.name if project.client_brand else 'Client')
    proj = _sanitize(project.name)

    channel = resolved.get('channel')
    if channel is not None:
        country = channel.posm_country or ''
        country_display = GULF_REGION_NAMES.get(country, country.title())
        if channel.posm_customer_id:
            from app.modules.core.shared.models import ProjectCustomer
            pc = ProjectCustomer.query.get(channel.posm_customer_id)
            posm_rev = (pc.posm_revision_count or 0) if pc else 0
            label = 'Initial' if posm_rev == 0 else f'Revision {posm_rev}'
            customer = _sanitize(pc.customer.name if (pc and pc.customer) else 'Customer')
            return f'{client} - {proj} - {country_display} - {customer} - POSM - {label}'
        if country:
            counts = project.posm_country_revision_counts or {}
            posm_rev = counts.get(country, 0)
            label = 'Initial' if posm_rev == 0 else f'Revision {posm_rev}'
            return f'{client} - {proj} - {country_display} - POSM - {label}'
        is_revised = (project.revision_count or 0) > 0
        label = 'Initial' if not is_revised else f'Revision {project.revision_count}'
        return f'{client} - {proj} - POSM - {label}'

    if project.brief_type == 'ccm':
        ckv_rev = project.ckv_revision_count or 0
        label = 'Initial' if ckv_rev == 0 else f'Revision {ckv_rev}'
        return f'{client} - {proj} - Concept & KV - {label}'

    is_revised = (project.revision_count or 0) > 0
    label = 'Initial' if not is_revised else f'Revision {project.revision_count}'
    return f'{client} - {proj} - {label}'


@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/draft/submit-to-client', methods=['POST'])
@login_required
def overlay_submissions_submit_to_client(project_id):
    """Send the reviewed draft to the client (review_submissions only): zip the
    cached files, upload the zip to the NAS under the canonical name, clear the
    cache, and move the submission and its scope's statuses to
    submitted_to_client. Handles Standard, C&CM Concept & KV, and POSM scopes.

    Body (JSON): scope, customer_id, keep_revision_label (optional).
    """
    import re
    from app.modules.core.shared.models import ProjectSubmissionFile, ProjectSubmissionEvent
    from app.modules.core.shared.services.status_tracking import record_deliverable_status, sync_project_pipeline_status
    from app.modules.core.shared.services.notifications import notify_of_submission_to_client
    from app.modules.core.shared.services.achievements import check_achievements
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.projects.lib.submission_cache import build_zip_bytes, clear_submission_cache
    from app.modules.core.shared.services.nas import build_file_path, upload_app_file
    from app.modules.core.shared.extensions import db
    from datetime import datetime as dt
    from flask import jsonify, current_app

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not can('review_submissions', actor):
        return jsonify({'success': False, 'error': 'You do not have permission to submit to client.'}), 403

    blocked = submissions_blocked_reason(project)
    if blocked:
        return jsonify({'success': False, 'error': blocked}), 409

    data = request.get_json() or {}
    scope = data.get('scope', 'ckv')
    customer_id = data.get('customer_id')
    keep_revision_label = bool(data.get('keep_revision_label'))

    resolved = _resolve_submission_scope(project, scope, customer_id)

    draft = _get_active_draft(project, resolved)
    if not draft:
        return jsonify({'success': False, 'error': 'No active submission to send.'}), 400
    if draft.workflow_status != 'internal_review' or draft.is_being_edited:
        return jsonify({'success': False,
                        'error': 'The deck must be in internal review (not mid-edit) before submitting to client.'}), 400

    _sent = _get_sent_submission(project, resolved)

    # "Do not increase revision counter": a resend (e.g. wrong file attached)
    # reuses the sent deck's name with a " (N)" suffix that counts up
    # (2) -> (3) -> ..., so it never collides with the sent deck.
    if keep_revision_label and _sent is not None:
        sent_base = _sent.original_filename.rsplit('.', 1)[0]
        m = re.match(r'^(.*) \((\d+)\)$', sent_base)
        base_name = f'{m.group(1)} ({int(m.group(2)) + 1})' if m else f'{sent_base} (2)'
    else:
        # Don't overwrite the deck already with the client. The name only
        # changes after a Client Revision bumps the scope's counter.
        if _sent is not None and f'{_canonical_deck_basename(project, resolved)}.zip' == _sent.original_filename:
            return jsonify({'success': False,
                            'error': 'A deck is already with the client for this scope — request a Client Revision first.'}), 400
        base_name = _canonical_deck_basename(project, resolved)

    cached_files = ProjectSubmissionFile.query.filter_by(
        submission_id=draft.id, storage_location='cache'
    ).order_by(
        ProjectSubmissionFile.is_main_deck.desc(),
        ProjectSubmissionFile.uploaded_at.asc(),
    ).all()
    if not cached_files:
        return jsonify({'success': False, 'error': 'There are no files to send.'}), 400

    main_deck = next((f for f in cached_files if f.is_main_deck), None)
    if not main_deck:
        return jsonify({'success': False, 'error': 'Flag a main deck before submitting.'}), 400

    # ── Canonical naming ──
    # The NAS zip is base_name.zip. Inside it the main deck is renamed to
    # base_name + its own extension; other files keep their uploaded names.
    main_ext = (main_deck.file_type or main_deck.original_filename.rsplit('.', 1)[-1]).lower()
    main_deck.original_filename = f'{base_name}.{main_ext}'
    zip_name = f'{base_name}.zip'

    # Cache and DB change only after the NAS write succeeds, so a failed
    # upload leaves the draft intact and re-sendable.
    entries = [{'local_cache_path': f.local_cache_path, 'arcname': f.original_filename}
               for f in cached_files]
    zip_bytes = build_zip_bytes(entries)

    nas_folder = build_file_path(project, 'Submissions', zip_name).rsplit('/', 1)[0]
    try:
        upload_app_file(zip_bytes, nas_folder, zip_name)
    except RuntimeError as e:
        current_app.logger.error(
            f'Submit-to-client zip upload failed (project={project_id}, draft={draft.id}): {e}')
        return jsonify({'success': False,
                        'error': 'Could not save the deck to storage. Nothing was sent — please try again.'}), 502

    # From here, file rows resolve to members of the zip (see
    # _load_submission_file_bytes in files.py).
    for f in cached_files:
        f.storage_location = 'nas'
        f.local_cache_path = None
    draft.original_filename = zip_name
    draft.filename = zip_name
    draft.workflow_status = 'sent_to_client'
    draft.submitted_to_client_at = dt.utcnow()
    draft.submitted_by_id = actor.id

    # The new deck supersedes the prior sent one, which stays in History.
    if _sent is not None:
        _sent.is_active = False

    # ── Status transitions, by scope ──
    # revision_count is not incremented here (Client Revision does that).
    channel = resolved['channel']
    if channel is not None:
        # POSM: advance the channel and its included deliverables.
        channel.status = 'submitted_to_client'
        for link in draft.included_deliverables:
            if link.deliverable:
                record_deliverable_status(link.deliverable, 'submitted_to_client', actor)
    elif project.brief_type == 'ccm':
        # C&CM Concept & KV: advance only the included concept/KV statuses;
        # deliverables wait for the POSM stage.
        if draft.includes_concept and project.has_concept:
            project.concept_status = 'submitted_to_client'
        if draft.includes_kv and project.has_kv:
            project.kv_status = 'submitted_to_client'
    else:
        # Standard: advance included deliverables and stamp the current
        # revision_count on them once revised.
        is_revised_submission = (project.revision_count or 0) > 0
        included_ids = {link.deliverable_id for link in draft.included_deliverables if link.deliverable_id}
        for deliverable in project.project_deliverables:
            if deliverable.id in included_ids:
                record_deliverable_status(deliverable, 'submitted_to_client', actor)
                if is_revised_submission:
                    deliverable.revision_count = project.revision_count
        if project.concept_status:
            project.concept_status = 'submitted_to_client'
        if project.kv_status:
            project.kv_status = 'submitted_to_client'

    # The project pill is a deliverable roll-up, for all three scopes.
    sync_project_pipeline_status(project, actor)

    db.session.add(ProjectSubmissionEvent(
        submission_id=draft.id, event_type='submitted_to_client',
        author_id=actor.id, message=None,
    ))
    db.session.commit()

    # Safe now: the files live in the NAS zip.
    clear_submission_cache(project.id, draft.id)

    log_activity('submitted_to_client',
                 f'"{project.name}" submitted to client by {actor.name}',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    notify_of_submission_to_client(project, triggered_by=actor)
    check_achievements(actor, 'project_submitted')

    client_email = project.client_brand.contact_email if project.client_brand else None
    return jsonify({'success': True, 'client_email': client_email or '', 'project_name': project.name})

@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/submit-summary')
@login_required
def overlay_submissions_submit_summary(project_id):
    """
    Read-only fragment for the Submit to Client modal: the included
    deliverables (or Concept/KV), already-approved ones as read-only
    indicators (sending never changes their status), the expected zip name,
    and the files being sent.
    """
    from app.modules.core.shared.models import ProjectSubmissionFile, Deliverable
    from app.modules.core.shared.lib.status_vocabulary import derive_deliverable_status
    from flask import jsonify

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not can('review_submissions', actor):
        return jsonify({'success': False, 'error': 'You do not have permission to submit to client.'}), 403

    scope = request.args.get('scope', 'ckv')
    customer_id = request.args.get('customer_id', type=int)
    resolved = _resolve_submission_scope(project, scope, customer_id)

    draft = _get_active_draft(project, resolved)
    if not draft or draft.workflow_status != 'internal_review' or draft.is_being_edited:
        return jsonify({'success': False,
                        'error': 'The deck must be in internal review (not mid-edit) before submitting to client.'}), 400

    cached_files = ProjectSubmissionFile.query.filter_by(
        submission_id=draft.id, storage_location='cache'
    ).order_by(
        ProjectSubmissionFile.is_main_deck.desc(),
        ProjectSubmissionFile.uploaded_at.asc(),
    ).all()
    main_deck = next((f for f in cached_files if f.is_main_deck), None)
    if not main_deck:
        return jsonify({'success': False, 'error': 'Flag a main deck before submitting.'}), 400

    # The default name. With "Do not increase revision counter" ticked, the
    # sent name gets a " (N)" suffix instead (see submit_to_client).
    expected_filename = f'{_canonical_deck_basename(project, resolved)}.zip'

    # The "Do not increase revision counter" checkbox shows only when a deck
    # is already with the client.
    has_sent_submission = _get_sent_submission(project, resolved) is not None

    # C&CM Concept & KV uses concept/KV toggles. Other scopes split
    # deliverables into included vs already-approved indicators.
    is_ckv_toggle_scope = resolved['phase'] == 'concept_kv' and project.brief_type == 'ccm'
    included = []
    indicators = []
    if not is_ckv_toggle_scope:
        if resolved['phase'] == 'concept_kv':
            scope_deliverables = Deliverable.query.filter_by(
                project_id=project.id, project_customer_id=None
            ).order_by(Deliverable.id).all()
        else:
            scope_deliverables = Deliverable.query.filter_by(
                project_id=project.id, project_customer_id = resolved['posm_customer_id']
            ).order_by(Deliverable.id).all()
        included_ids = {link.deliverable_id for link in draft.included_deliverables if link.deliverable_id}
        for d in scope_deliverables:
            entry = {'deliverable': d, 'pill': derive_deliverable_status(d)}
            if d.id in included_ids:
                included.append(entry)
            elif d.status == 'approved':
                indicators.append(entry)

    return render_template(
        'project_overlay/_submissions_submit_summary.html',
        project=project, scope=scope, customer_id=customer_id,
        expected_filename=expected_filename,
        files=cached_files, included=included, indicators=indicators,
        is_ckv_toggle_scope=is_ckv_toggle_scope,
        includes_concept=draft.includes_concept, includes_kv=draft.includes_kv,
        has_sent_submission=has_sent_submission,
    )
@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/client-revision', methods=['POST'])
@login_required
def overlay_submissions_client_revision(project_id):
    """
    Record a client revision on the deck with the client, for any scope.
    Bumps the scope's revision counter (which unblocks the next Submit to
    Client), moves the scope's deliverables or Concept/KV to
    revision_in_queue, logs a 'client_revision' event on the sent deck, and
    notifies assigned designers. The sent deck stays active until the next
    Submit to Client supersedes it.
    """
    from app.modules.core.shared.models import ProjectSubmissionEvent, ProjectDesigner
    from app.modules.core.shared.services.status_tracking import record_deliverable_status, sync_project_pipeline_status
    from app.modules.core.shared.services.notifications import create_notification
    from app.modules.core.shared.lib.utils import strip_html, log_activity
    from app.modules.core.shared.extensions import db
    from flask import jsonify

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not can('review_submissions', actor):
        return jsonify({'success': False, 'error': 'You do not have permission to request a client revision.'}), 403

    blocked = submissions_blocked_reason(project)
    if blocked:
        return jsonify({'success': False, 'error': blocked}), 409

    data = request.get_json() or {}
    scope = data.get('scope', 'ckv')
    customer_id = data.get('customer_id')
    message = (data.get('message') or '').strip()
    if not message or not strip_html(message).strip():
        return jsonify({'success': False, 'error': 'Please describe the revision the client requested.'}), 400

    resolved = _resolve_submission_scope(project, scope, customer_id)

    sent = _get_sent_submission(project, resolved)
    if sent is None:
        return jsonify({'success': False, 'error': 'There is no deck with the client to revise.'}), 400
    if any(e.event_type == 'client_revision' for e in sent.events):
        return jsonify({'success': False, 'error': 'A client revision has already been requested for this deck.'}), 400

    # Standard revises the whole project and all its deliverables. C&CM
    # Concept & KV and POSM touch only their own scope's counter and statuses.
    channel = resolved['channel']
    if channel is not None:
        # POSM: bump the customer (or country) counter and move the channel
        # and the sent deck's deliverables into revision.
        channel.status = 'revision_in_queue'
        if channel.posm_customer_id:
            from app.modules.core.shared.models import ProjectCustomer
            pc = ProjectCustomer.query.get(channel.posm_customer_id)
            new_rev = ((pc.posm_revision_count or 0) + 1) if pc else 1
            if pc:
                pc.posm_revision_count = new_rev
        elif channel.posm_country:
            counts = dict(project.posm_country_revision_counts or {})
            counts[channel.posm_country] = counts.get(channel.posm_country, 0) + 1
            project.posm_country_revision_counts = counts
            new_rev = counts[channel.posm_country]
        else:
            new_rev = (project.revision_count or 0) + 1
            project.revision_count = new_rev
        for link in sent.included_deliverables:
            if link.deliverable:
                record_deliverable_status(link.deliverable, 'revision_in_queue', actor)
                link.deliverable.revision_count = new_rev
        rev_label = f'#{new_rev}'
    elif project.brief_type == 'ccm':
        # C&CM Concept & KV: bump its counter and move only the included
        # concept/KV statuses. Deliverables are untouched until POSM.
        project.ckv_revision_count = (project.ckv_revision_count or 0) + 1
        if sent.includes_concept and project.has_concept:
            project.concept_status = 'revision_in_queue'
        if sent.includes_kv and project.has_kv:
            project.kv_status = 'revision_in_queue'
        rev_label = f'#{project.ckv_revision_count}'
    else:
        project.revision_count = (project.revision_count or 0) + 1
        for deliverable in project.project_deliverables:
            record_deliverable_status(deliverable, 'revision_in_queue', actor)
            deliverable.revision_count = project.revision_count
        rev_label = f'#{project.revision_count}'

    # The project pill is a deliverable roll-up, so this can move a project
    # back to In Design. The earlier client-approval timestamp is kept (see
    # status_tracking.py's project_client_approved_at()).
    sync_project_pipeline_status(project, actor)

    db.session.add(ProjectSubmissionEvent(
        submission_id=sent.id, event_type='client_revision',
        author_id=actor.id, message=message,
    ))
    db.session.commit()

    for assignment in ProjectDesigner.query.filter_by(project_id=project.id).all():
        if assignment.designer and assignment.designer.id != actor.id:
            create_notification(
                recipient=assignment.designer,
                message=f'Client revision {rev_label} requested on "{project.name}" by {actor.name}.',
                notification_type='revision_requested',
                project=project,
                triggered_by=actor,
            )

    log_activity('revision_requested',
                 f'Client revision {rev_label} requested on "{project.name}" by {actor.name}: {strip_html(message)[:100]}',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/submissions/approve', methods=['POST'])
@login_required
def overlay_submissions_approve(project_id):
    """
    Client approval of some or all of the sent deck. Partial approval lets
    some deliverables move to Pre-Production while others stay in design.
    Not allowed once a client revision is pending on the deck.

    Body (JSON): scope, customer_id, deliverable_ids (omitted = all pending;
    an empty list is rejected as "nothing selected"), note (optional, stored
    on the client_approval event). C&CM Concept & KV is approved as a pair.

    A channel, then the project, is marked fully approved only once EVERY
    deliverable in it is approved, not just this deck's.
    """
    from app.modules.core.shared.models import Deliverable, ProjectPosmChannel, ProjectSubmissionEvent, ProjectSubmissionEventDeliverable
    from app.modules.core.shared.services.status_tracking import record_deliverable_status, sync_project_pipeline_status
    from app.modules.core.shared.lib.status_vocabulary import derive_preproduction_needs
    from app.modules.core.shared.services.notifications import notify_of_project_approved
    from app.modules.core.shared.services.achievements import check_achievements
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.extensions import db
    from datetime import datetime as dt
    from flask import jsonify

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not can('review_submissions', actor):
        return jsonify({'success': False, 'error': 'You do not have permission to approve this submission.'}), 403

    blocked = submissions_blocked_reason(project)
    if blocked:
        return jsonify({'success': False, 'error': blocked}), 409

    data = request.get_json() or {}
    scope = data.get('scope', 'ckv')
    customer_id = data.get('customer_id')
    deliverable_ids = data.get('deliverable_ids')
    note = (data.get('note') or '').strip()
    # None means "approve all"; an empty list is rejected below, so don't
    # test truthiness. Cast to int: DeliverablePicker.getSelectedIds() sends
    # strings, which would never match Deliverable.id in a Python set.
    deliverable_id_set = None
    if deliverable_ids is not None:
        try:
            deliverable_id_set = {int(i) for i in deliverable_ids}
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'Invalid deliverable selection.'}), 400

    resolved = _resolve_submission_scope(project, scope, customer_id)

    sent = _get_sent_submission(project, resolved)
    if sent is None:
        return jsonify({'success': False, 'error': 'There is no deck with the client to approve.'}), 400
    if any(e.event_type == 'client_revision' for e in sent.events):
        return jsonify({'success': False,
                        'error': 'A client revision is already pending on this deck — nothing to approve.'}), 400

    now = dt.utcnow()
    all_approved = False # True if this call made the whole project approved
    channel = resolved['channel']
    approved_deliverables_this_call = [] # linked to the client_approval event below

    if channel is not None:
        # ── POSM ────────────────────────────────────────────────────────
        if channel.status == 'approved':
            return jsonify({'success': False, 'error': 'This channel is already approved.'}), 400

        pending = [
            link.deliverable for link in sent.included_deliverables
            if link.deliverable and link.deliverable.status != 'approved'
            and (deliverable_id_set is None or link.deliverable.id in deliverable_id_set)
        ]
        if deliverable_id_set is not None and not pending:
            return jsonify({'success': False, 'error': 'Select at least one deliverable to approve.'}), 400
        for d in pending:
            record_deliverable_status(d, 'approved', actor)
            # Set the Pre-Production streams on approval.
            d.needs_2d, d.needs_3d, d.needs_technical = derive_preproduction_needs(d)
        approved_deliverables_this_call = pending

        # The channel is approved once every deliverable it covers is.
        # A per-customer channel covers one customer; a legacy region-level
        # channel (no customer) covers the whole region.
        if channel.posm_customer_id:
            channel_deliverables = Deliverable.query.filter_by(
                project_id=project.id, project_customer_id=channel.posm_customer_id
            ).all()
        else:
            region_pc_ids = [
                pc.id for pc in project.project_customers
                if pc.customer.region == channel.posm_country and not pc.cancelled
            ]
            channel_deliverables = Deliverable.query.filter(
                Deliverable.project_id == project.id,
                Deliverable.project_customer_id.in_(region_pc_ids)
            ).all() if region_pc_ids else []

        if channel_deliverables and all(d.status == 'approved' for d in channel_deliverables):
            channel.status = 'approved'
            channel.approved_at = now
            channel.approved_by_id = actor.id

            # The project is fully approved once every channel and Concept/KV
            # (if any) is approved.
            all_channels = ProjectPosmChannel.query.filter_by(project_id=project.id).all()
            if all_channels and all(c.status == 'approved' for c in all_channels):
                ckv_gate = True
                if project.has_concept and project.concept_status != 'approved':
                    ckv_gate = False
                if project.has_kv and project.kv_status != 'approved':
                    ckv_gate = False
                if ckv_gate:
                    project.approved_at = now
                    project.approved_by_id = actor.id
                    all_approved = True

    elif project.brief_type == 'ccm':
        # ── C&CM Concept & KV: approved as a pair ──
        if project.concept_status == 'approved' and project.kv_status == 'approved':
            return jsonify({'success': False, 'error': 'Concept & KV is already approved.'}), 400
        if project.has_concept:
            project.concept_status = 'approved'
        if project.has_kv:
            project.kv_status = 'approved'
        project.concept_approved_at = now
        project.concept_approved_by_id = actor.id

        # With no channels yet, the project is not marked fully approved.
        all_channels = ProjectPosmChannel.query.filter_by(project_id=project.id).all()
        if all_channels and all(c.status == 'approved' for c in all_channels):
            project.approved_at = now
            project.approved_by_id = actor.id
            all_approved = True

    else:
        # ── Standard Brief ─────────────────────────────────────────────
        if project.project_status == 'approved':
            return jsonify({'success': False, 'error': 'This project is already approved.'}), 400

        pending = [
            d for d in project.project_deliverables
            if d.status != 'approved' and (deliverable_id_set is None or d.id in deliverable_id_set)
        ]
        if deliverable_id_set is not None and not pending:
            return jsonify({'success': False, 'error': 'Select at least one deliverable to approve.'}), 400
        for d in pending:
            record_deliverable_status(d, 'approved', actor)
            # Set the Pre-Production streams on approval.
            d.needs_2d, d.needs_3d, d.needs_technical = derive_preproduction_needs(d)
        approved_deliverables_this_call = pending

        if all(d.status == 'approved' for d in project.project_deliverables):
            project.approved_at = now
            project.approved_by_id = actor.id
            all_approved = True
            if project.concept_status:
                project.concept_status = 'approved'
            if project.kv_status:
                project.kv_status = 'approved'

    # The project pill is a deliverable roll-up, independent of all_approved:
    # Concept/KV gates the "fully approved" notification and timestamp, not
    # the pill.
    sync_project_pipeline_status(project, actor)

    # Always log the event, even with no note, so the timeline records who
    # approved what. Pre-Production reads these events and their deliverable
    # links to show CS's notes. Concept & KV approvals have no links.
    approval_event = ProjectSubmissionEvent(
        submission_id=sent.id, event_type='client_approval',
        author_id=actor.id, message=note or None,
    )
    db.session.add(approval_event)
    db.session.flush() # need approval_event.id for the link rows below
    for d in approved_deliverables_this_call:
        db.session.add(ProjectSubmissionEventDeliverable(event_id=approval_event.id, deliverable_id=d.id))

    db.session.commit()

    log_activity(
        'project_approved' if all_approved else 'deliverables_approved',
        f'"{project.name}" approved by {actor.name}' if all_approved
        else f'Deliverables partially approved on "{project.name}" by {actor.name}',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id
    )

    if all_approved:
        notify_of_project_approved(project, triggered_by=actor)
        check_achievements(actor, 'project_approved')

    return jsonify({'success': True, 'all_approved': all_approved})
