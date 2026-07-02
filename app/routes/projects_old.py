import os
import re
import uuid
from datetime import date
from flask import (Blueprint, render_template, redirect, url_for, flash, request, current_app, send_from_directory, jsonify, abort, session)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import (Project, ProjectDesigner, Scope, User, Client,
                        Customer, DeliverableType, ProjectRegion,
                        ProjectCustomer, Deliverable, DeliverableAssignment,
                        DeliverableTypeDiscipline)
from app.decorators import role_required
from datetime import date, datetime
from app.notifications import (
    notify_team_leads_of_new_project, notify_cs_lead_of_assignment,
    notify_designers_of_revision_flag, notify_cs_of_revision_submitted,
    notify_cs_of_brief_flag, notify_flag_reply, notify_cs_of_flag_resolved,
    notify_designer_of_concept_kv_assignment, notify_cs_of_lead_change,
    create_notification, notify_cs_of_project_started,
    notify_of_submission_to_client, notify_of_project_approved,
    notify_lead_designers_of_project_started
)
from app.utils import log_activity

projects = Blueprint('projects', __name__)

@projects.route('/projects/create', methods=['GET'])
@login_required
@role_required('admin', 'cs', 'management')
def create():
    cs_users = User.query.filter(
        User.role.in_(['cs', 'admin'])
    ).order_by(User.name).all()

    clients = Client.query.order_by(Client.name).all()

    customers_raw = {
    'uae': Customer.query.filter_by(region='uae').order_by(Customer.name).all(),
    'kuwait': Customer.query.filter_by(region='kuwait').order_by(Customer.name).all(),
    'qatar': Customer.query.filter_by(region='qatar').order_by(Customer.name).all(),
    'bahrain': Customer.query.filter_by(region='bahrain').order_by(Customer.name).all(),
    'oman': Customer.query.filter_by(region='oman').order_by(Customer.name).all(),
    }

    customers_by_region = {
    region: [{'id': c.id, 'name': c.name} for c in customers]
    for region, customers in customers_raw.items()
    }

    draft = None
    draft_id = request.args.get('draft_id')
    if draft_id:
        candidate = Project.query.get(int(draft_id))
        if candidate and candidate.created_by_id == current_user.id and candidate.project_status == 'draft':
            draft = candidate
    
    has_other_drafts = Project.query.filter_by(
         created_by_id=current_user.id,
         project_status='draft'
    ).count() > 0

    from app.models import DesignType, DesignDirection
    design_types = DesignType.query.order_by(DesignType.name).all()
    design_directions = DesignDirection.query.order_by(DesignDirection.name).all()

    return render_template(
        'projects/create.html',
        cs_users=cs_users,
        clients=clients,
        customers_by_region=customers_by_region,
        draft=draft,
        has_other_drafts=has_other_drafts,
        design_types=design_types,
        design_directions=design_directions,
        today=date.today().isoformat(),
    )

@projects.route('/projects/<int:project_id>/edit', methods=['GET'])
@login_required
@role_required('admin', 'cs', 'management')
def edit_project(project_id):
    project = Project.query.get_or_404(project_id)

    if current_user.role == 'cs' and project.cs_lead_id != current_user.id:
        abort(403)

    cs_users = User.query.filter(User.role.in_(['cs', 'admin'])).order_by(User.name).all()
    clients = Client.query.order_by(Client.name).all()

    customers_raw = {
        'uae': Customer.query.filter_by(region='uae').order_by(Customer.name).all(),
        'kuwait': Customer.query.filter_by(region='kuwait').order_by(Customer.name).all(),
        'qatar': Customer.query.filter_by(region='qatar').order_by(Customer.name).all(),
        'bahrain': Customer.query.filter_by(region='bahrain').order_by(Customer.name).all(),
        'oman': Customer.query.filter_by(region='oman').order_by(Customer.name).all(),
    }
    customers_by_region = {
        region: [{'id': c.id, 'name': c.name} for c in customers]
        for region, customers in customers_raw.items()
    }

    existing_customers = []
    for pc in project.project_customers:
        existing_customers.append({
            'customer_id': pc.customer_id,
            'region': pc.customer.region,
            'design_deadline': pc.design_deadline.isoformat() if pc.design_deadline else None,
            'design_deadline_time': pc.design_deadline_time.strftime('%H:%M') if pc.design_deadline_time else None,
            'installation_date': pc.installation_date.isoformat() if pc.installation_date else None,
        })

    existing_deliverables = []
    for d in project.project_deliverables:
        if d.project_customer_id is None:
            continue  # Skip standard brief deliverables (added post-creation)
        disciplines = [dtd.team.lower() for dtd in d.deliverable_type.disciplines] if d.deliverable_type else []
        existing_deliverables.append({
            'customer_id': d.project_customer.customer_id,
            'type_id': d.deliverable_type_id,
            'name': d.name,
            'disciplines': disciplines,
        })

    from app.models import DesignType, DesignDirection
    design_types = DesignType.query.order_by(DesignType.name).all()
    design_directions = DesignDirection.query.order_by(DesignDirection.name).all()

    existing_standard_deliverables = [
        {
            'name': d.name,
            'design_deadline': d.design_deadline.isoformat() if d.design_deadline else None,
            'design_deadline_time': d.design_deadline_time.strftime('%H:%M') if d.design_deadline_time else None,
            'teams': [t.strip() for t in d.teams.split(',')] if d.teams else []
        }
        for d in Deliverable.query.filter_by(
            project_id=project.id, project_customer_id=None
        ).order_by(Deliverable.created_at).all()
    ]

    return render_template(
        'projects/create.html',
        draft=project,
        edit_mode=True,
        edit_project_id=project.id,
        cs_users=cs_users,
        clients=clients,
        customers_by_region=customers_by_region,
        existing_customers=existing_customers,
        existing_deliverables=existing_deliverables,
        has_other_drafts=False,
        design_types=design_types,
        design_directions=design_directions,
        existing_standard_deliverables=existing_standard_deliverables,
        today=date.today().isoformat(),
    )


@projects.route('/projects/<int:project_id>/update', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def update_project(project_id):
    project = Project.query.get_or_404(project_id)

    if current_user.role == 'cs' and project.cs_lead_id != current_user.id:
        abort(403)

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        def parse_date(val):
            if not val:
                return None
            try:
                from datetime import datetime
                return datetime.strptime(val, '%Y-%m-%d').date()
            except ValueError:
                return None

        project.name = data['name']
        project.client_id = int(data['client_id']) if data.get('client_id') else project.client_id
        project.cs_lead_id = int(data['cs_lead_id']) if data.get('cs_lead_id') else project.cs_lead_id
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
        project.brief_type = data.get('brief_type', project.brief_type)
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
        # briefing_date intentionally excluded — locked for accountability
        project.first_output_deadline = parse_date(data.get('first_output_deadline'))
        project.execution_date = parse_date(data.get('final_deadline'))

        db.session.flush()

        if project.brief_type == 'standard':
            # Update standard brief fields
            project.design_type_id = int(data['design_type_id']) if data.get('design_type_id') else None
            project.design_direction_id = int(data['design_direction_id']) if data.get('design_direction_id') else None
            project.client_expectation = data.get('client_expectation')
            project.what_to_avoid = data.get('what_to_avoid')
            project.additional_information = data.get('additional_information')

            # Upsert standard deliverables — preserves status/assignments on existing ones.
            # Only deliverables removed from the form are deleted; existing ones get their
            # deadline and teams updated without touching their status or assignments.
            def _norm_del(x):
                if isinstance(x, str):
                    return {'name': x.strip(), 'design_deadline': None, 'teams': []}
                return {
                    'name': (x.get('name') or '').strip(),
                    'design_deadline': x.get('design_deadline'),
                    'teams': x.get('teams') or [],
                }

            submitted_items = [_norm_del(x) for x in data.get('standard_deliverables', [])]
            submitted_items = [i for i in submitted_items if i['name']]
            submitted_names = {i['name'] for i in submitted_items}

            # Index existing deliverables by name
            existing_std = {
                d.name: d
                for d in Deliverable.query.filter_by(
                    project_id=project.id, project_customer_id=None
                ).all()
            }

            # Delete deliverables removed from the form
            for name, d in existing_std.items():
                if name not in submitted_names:
                    db.session.delete(d)

            # Update existing / insert new
            for item in submitted_items:
                raw_dd = item.get('design_deadline')
                del_deadline = parse_date(raw_dd) if raw_dd else None
                raw_time = item.get('design_deadline_time')
                del_time = datetime.strptime(raw_time, '%H:%M').time() if raw_time else None
                del_teams = ','.join(item['teams']) if item['teams'] else None
                if item['name'] in existing_std:
                    # Keep status and assignments — only refresh editable fields
                    d = existing_std[item['name']]
                    d.design_deadline = del_deadline
                    d.design_deadline_time = del_time
                    d.teams = del_teams
                else:
                    db.session.add(Deliverable(
                        project_id=project.id,
                        project_customer_id=None,
                        deliverable_type_id=None,
                        name=item['name'],
                        design_deadline=del_deadline,
                        design_deadline_time=del_time,
                        teams=del_teams,
                        status='in_queue',
                        created_by=current_user
                    ))
        else:
            ProjectRegion.query.filter_by(project_id=project.id).delete()
            for region_name in data.get('regions', []):
                db.session.add(ProjectRegion(project_id=project.id, region=region_name))

            # --- Stage 1: Load existing ProjectCustomers by customer_id ---
            existing_pcs = {
                pc.customer_id: pc
                for pc in ProjectCustomer.query.filter_by(project_id=project.id).all()
            }

            # --- Stage 2:upsert ---
            customer_dates = data.get('customer_dates', {})
            submitted_customer_ids = set()
            for item in data.get ('deliverables', []):
                submitted_customer_ids.add(int(item['customer_id']))

            # Delete customers no longer in the submitted list
            for cid, pc in existing_pcs.items():
                if cid not in submitted_customer_ids:
                    from app.models import ProjectSubmission
                    has_submissions = ProjectSubmission.query.filter_by(
                        posm_customer_id=pc.id
                    ).first()
                    if not has_submissions:
                        db.session.delete(pc)
                                
            db.session.flush()

            # Update or insert
            customer_map = {}
            for customer_id in submitted_customer_ids:
                dates = customer_dates.get(str(customer_id), {})
                raw_time = dates.get('design_deadline_time')
                parsed_time = datetime.strptime(raw_time, '%H:%M').time() if raw_time else None

                if customer_id in existing_pcs:
                    # Preserve the row and its ID. Update deadline fields
                    pc = existing_pcs[customer_id]
                    pc.design_deadline = parse_date(dates.get('design_deadline'))
                    pc.design_deadline_time = parsed_time
                    pc.installation_date = parse_date(dates.get('installation_date'))
                else:
                    # New customer, insert fresh row
                    pc = ProjectCustomer(
                        project_id=project.id,
                        customer_id=customer_id,
                        design_deadline=parse_date(dates.get('design_deadline')),
                        design_deadline_time=parsed_time,
                        installation_date=parse_date(dates.get('installation_date')),
                    )
                    db.session.add(pc)
                
                db.session.flush()
                customer_map[customer_id] = pc.id
            
            # --- Stage 3: rebuild deliverables for surviving customers ---
            for pc_id in customer_map.values():
                Deliverable.query.filter_by(
                    project_customer_id=pc_id
                ).delete(synchronize_session=False)
            db.session.flush()

            for item in data.get('deliverables', []):
                customer_id = int(item['customer_id'])
                db.session.add(Deliverable (
                    project_id=project.id,
                    project_customer_id=customer_map[customer_id],
                    deliverable_type_id=int(item['type_id']) if item.get('type_id') and item['type_id'] != 'custom' else None,
                    name=item['name'],
                    created_by=current_user
                ))
                
        db.session.commit()

        log_activity('project_edited', f'Project "{project.name}" was edited by {current_user.name}',
                     user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)

        return jsonify({'success': True, 'redirect_url': url_for('project_detail.detail', project_id=project.id)})

    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Something went wrong. Please try again.'}), 500


@projects.route('/projects/autosave', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def autosave():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        draft_id = data.get('draft_id')
        draft = None

        if draft_id:
            candidate = Project.query.get(int(draft_id))
            if candidate and candidate.created_by_id == current_user.id and candidate.project_status == 'draft':
                draft = candidate
            elif candidate and candidate.project_status != 'draft':
                return jsonify({'success': False, 'error': 'Project already submitted'}), 400

        default_scope = Scope.query.filter_by(active=True).first()

        if not draft:
            draft = Project(
                name=data.get('name', '').strip() or 'Untitled Draft',
                client='TBD',
                cs_lead_id=int(data['cs_lead_id']) if data.get('cs_lead_id') else current_user.id,
                creator=current_user,
                project_status='draft',
                scope_id=default_scope.id if default_scope else 1
            )
            db.session.add(draft)
            db.session.flush()

        draft.name = data.get('name', '').strip() or 'Untitled Draft'

        if data.get('cs_lead_id'):
            draft.cs_lead_id = int(data['cs_lead_id'])

        if data.get('client_id'):
            draft.client_id = int(data['client_id'])

        if data.get('job_number'):
            job_num = data['job_number'].strip()
            conflict = Project.query.filter(
                Project.job_number == job_num,
                Project.id != draft.id
            ).first()
            if not conflict:
                draft.job_number = job_num or None

        if data.get('design_teams'):
            draft.design_teams_requested = ', '.join(data['design_teams'])

        if data.get('brief_type'):
            draft.brief_type = data['brief_type']

        if data.get('urgency'):
            draft.urgency = data['urgency']

        if data.get('required_output'):
            draft.required_output = data['required_output']

        if data.get('concept_deadline'):
            draft.concept_deadline = date.fromisoformat(data['concept_deadline'])
        raw_cdt = data.get('concept_deadline_time')
        draft.concept_deadline_time = datetime.strptime(raw_cdt, '%H:%M').time() if raw_cdt else None

        if data.get('concept_requirements') is not None:
            draft.campaign_notes = data['concept_requirements']

        if 'has_concept' in data:
            draft.has_concept = bool(data['has_concept'])

        if data.get('concept_options_required') is not None:
            draft.concept_options_required = data['concept_options_required']

        if 'has_kv' in data:
            draft.has_kv = bool(data['has_kv'])

        if data.get('kv_requirements') is not None:
            draft.kv_requirements = data['kv_requirements']

        if data.get('kv_deadline'):
            draft.kv_deadline = date.fromisoformat(data['kv_deadline'])

        if data.get('kv_options_required') is not None:
            draft.kv_options_required = data['kv_options_required']

        if data.get('briefing_date'):
            draft.briefing_date = date.fromisoformat(data['briefing_date'])

        if data.get('first_output_deadline'):
            draft.first_output_deadline = date.fromisoformat(data['first_output_deadline'])

        if data.get('final_deadline'):
            draft.execution_date = date.fromisoformat(data['final_deadline'])

        if data.get('installation_date'):
            draft.installation_date = date.fromisoformat(data['installation_date'])

        # Standard brief fields
        if data.get('design_type_id'):
            draft.design_type_id = int(data['design_type_id'])
        elif data.get('design_type_id') is None and 'design_type_id' in data:
            draft.design_type_id = None

        if data.get('design_direction_id'):
            draft.design_direction_id = int(data['design_direction_id'])
        elif data.get('design_direction_id') is None and 'design_direction_id' in data:
            draft.design_direction_id = None

        if data.get('client_expectation') is not None:
            draft.client_expectation = data['client_expectation']

        if data.get('what_to_avoid') is not None:
            draft.what_to_avoid = data['what_to_avoid']

        if data.get('additional_information') is not None:
            draft.additional_information = data['additional_information']

        draft.last_autosaved_at = datetime.now()
        db.session.commit()

        return jsonify({'success': True, 'draft_id': draft.id})

    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': 'Autosave failed'}), 500

@projects.route('/projects/<int:project_id>')
@login_required
def detail(project_id):
    project = Project.query.get_or_404(project_id)

    from app.models import ProjectSubmission, ProjectRevision
    import json as _json

    # Active submission: the deck currently under review or awaiting upload
    active_submission = ProjectSubmission.query.filter_by(
        project_id=project_id, is_active=True
    ).first()

    # For CCM projects with concept/KV: the active C&KV submission (separate from POSM channel submissions)
    ckv_submission = None
    if project.brief_type == 'ccm' and (project.has_concept or project.has_kv):
        ckv_submission = ProjectSubmission.query.filter_by(
            project_id=project_id, is_active=True, phase='concept_kv'
        ).first()

    # Submission history: only decks that were fully submitted to the client.
    # Drafts/flagged decks that were replaced are not in this list (their files were deleted).
    submitted_history = ProjectSubmission.query.filter(
        ProjectSubmission.project_id == project_id,
        ProjectSubmission.submitted_to_client_at.isnot(None)
    ).order_by(ProjectSubmission.submitted_to_client_at.desc()).all()

    # All inactive submissions that were NOT submitted to client (flagged drafts) — for completeness
    past_submissions = ProjectSubmission.query.filter_by(
        project_id=project_id, is_active=False
    ).order_by(ProjectSubmission.uploaded_at.desc()).all()

    # Deliverables as JSON for the submission deliverable picker.
    # For CCM briefs each deliverable has a project_customer_id — we pass the
    # customer name so the JS can group checkboxes by customer.
    # For standard briefs project_customer_id is null and no grouping is needed.
    all_deliverables_for_picker = Deliverable.query.filter_by(
        project_id=project_id
    ).order_by(Deliverable.created_at).all()

    deliverables_json = _json.dumps([
        {
            'id': d.id,
            'name': d.name,
            'status': d.status,
            # project_customer_id is None for standard brief deliverables
            'customer_id':   d.project_customer_id,
            'customer_name': d.project_customer.customer.name if d.project_customer else None
        }
        for d in all_deliverables_for_picker
    ])

    _d3 = User.query.filter(User.role.in_(['designer', 'team_lead']), User.team == '3D').order_by(User.name).all()
    _d2 = User.query.filter(User.role.in_(['designer', 'team_lead']), User.team == '2D').order_by(User.name).all()
    _dt = User.query.filter(User.role.in_(['designer', 'team_lead']), User.team == 'Technical').order_by(User.name).all()
    designers_by_team = {
        '3D': _d3, '3d': _d3,
        '2D': _d2, '2d': _d2,
        'Technical': _dt, 'technical': _dt,
    }

    assignments_by_team = {}
    for assignment in project.assigned_designers:
        assignments_by_team[assignment.team] = assignment

    brief_sections = {}
    for pc in project.project_customers:
        region = pc.customer.region
        if region not in brief_sections:
            brief_sections[region] = []
        brief_sections[region].append(pc)

    assignments_by_deliverable = {}
    for deliverable in project.project_deliverables:
        by_team = {}
        for assignment in deliverable.disciplines:
            by_team[assignment.team] = assignment  # DeliverableAssignment object (one per team)
        assignments_by_deliverable[deliverable.id] = by_team

    from app.models import BriefFlag
    open_flags = BriefFlag.query.filter_by(project_id=project_id, is_resolved=False).order_by(BriefFlag.created_at).all()
    all_flags = BriefFlag.query.filter_by(project_id=project_id).order_by(BriefFlag.created_at.desc()).all()

    # Standard brief deliverables (no project_customer_id)
    standard_deliverables = Deliverable.query.filter_by(
        project_id=project_id, project_customer_id=None
    ).order_by(Deliverable.created_at).all()

    standard_assignments_by_deliverable = {}
    for d in standard_deliverables:
        # Standard deliverables have one assignment per deliverable (not per team)
        asgn = d.disciplines[0] if d.disciplines else None
        standard_assignments_by_deliverable[d.id] = asgn

    # Designers per standard brief deliverable — filtered by each deliverable's own teams
    # Falls back to the project's design type teams, then all designers
    dt = project.design_type
    dt_teams = [t.strip() for t in dt.team.split(',') if t.strip()] if (dt and dt.team) else []

    def _designers_for_teams(teams):
        if not teams:
            return [d for team_list in designers_by_team.values() for d in team_list]
        pool = []
        for t in teams:
            pool.extend(designers_by_team.get(t, []))
        seen = set()
        return [d for d in pool if not (d.id in seen or seen.add(d.id))]

    # Fallback: project-level design type teams
    standard_designers = _designers_for_teams(dt_teams)
    standard_team = dt.team if (dt and dt.team) else None

    # Per-deliverable overrides when the deliverable itself has teams set
    standard_designers_by_deliverable = {}
    for d in standard_deliverables:
        if d.teams:
            d_teams = [t.strip() for t in d.teams.split(',') if t.strip()]
            standard_designers_by_deliverable[d.id] = _designers_for_teams(d_teams)
        else:
            standard_designers_by_deliverable[d.id] = standard_designers

    # ── Secondary CS ─────────────────────────────────────────────
    from app.models import ProjectSecondaryCS, ProjectSecondaryCsRegion
    from flask import session as _session

    _emulating_id = _session.get('emulating_user_id')
    _effective_user_id = _emulating_id if (_emulating_id and current_user.role == 'admin') else current_user.id

    secondary_cs_assignments = ProjectSecondaryCS.query.filter_by(project_id=project_id).all()
    secondary_cs_ids = {a.user_id for a in secondary_cs_assignments}
    is_secondary_cs = _effective_user_id in secondary_cs_ids

    # Regions the current effective user has subscribed to (for C&CM projects)
    my_secondary_regions = {
        r.region for r in ProjectSecondaryCsRegion.query.filter_by(
            project_id=project_id, user_id=_effective_user_id
        ).all()
    } if is_secondary_cs else set()

    # CS users available to be added (exclude lead and already-added)
    available_cs_users = User.query.filter(
        User.role == 'cs',
        User.id != project.cs_lead_id,
        ~User.id.in_(secondary_cs_ids) if secondary_cs_ids else True
    ).order_by(User.name).all()

    # Gulf regions: C&CM projects with customers in UAE/Kuwait/Qatar/Bahrain/Oman
    # submit POSM by region then customer, not just by customer.
    GULF_REGION_KEYS  = ['uae', 'kuwait', 'qatar', 'bahrain', 'oman']
    GULF_REGION_NAMES = {
        'uae': 'UAE', 'kuwait': 'Kuwait',
        'qatar': 'Qatar', 'bahrain': 'Bahrain', 'oman': 'Oman'
    }
    is_gulf = project.brief_type == 'ccm' and any(k in brief_sections for k in GULF_REGION_KEYS)

    # POSM is always active for Gulf C&CM projects — no manual "Begin POSM" step required
    posm_active = is_gulf

    # Pass each Gulf region with its customers so the JS can build the two-step picker.
    gulf_regions_json = _json.dumps([
        {
            'key': k,
            'name': GULF_REGION_NAMES[k],
            'customers': [
                {'id': pc.id, 'name': pc.customer.name, 'posm_revision_count': pc.posm_revision_count or 0}
                for pc in brief_sections[k]
            ]
        }
        for k in GULF_REGION_KEYS if k in brief_sections
    ]) if is_gulf else '[]'

    # Non-Gulf C&CM: flat customer list (kept for non-Gulf fallback)
    project_customers_json = _json.dumps([
        {'id': pc.id, 'name': pc.customer.name, 'posm_revision_count': pc.posm_revision_count or 0}
        for pc in project.project_customers
    ]) if (project.brief_type == 'ccm' and not is_gulf) else '[]'

    # Stored per-country POSM revision counts (Kuwait/Qatar/Bahrain/Oman)
    # Mirrors pc.posm_revision_count for UAE — incremented in send_revision.
    gulf_posm_counts = project.posm_country_revision_counts or {}

    # ── Parallel POSM channels ──────────────────────────────────────────────────
    # For Gulf C&CM projects: always build per-channel data for the pill UI.
    # Channels are auto-created on page load — no "Begin POSM" step required.
    # New customers added to the brief get a channel automatically.
    posm_channels_data = []
    if is_gulf:
        from app.models import ProjectPosmChannel, ProjectSubmission as _PS, ProjectRevision as _PR

        # Remove orphaned UAE channels — these arise when an edit deletes+recreates
        # ProjectCustomer records and PostgreSQL's ON DELETE SET NULL fires, leaving
        # a UAE channel with posm_customer_id=NULL. Delete them now so they get
        # recreated correctly below with the new ProjectCustomer ID.
        orphaned = [ch for ch in project.posm_channels
                    if ch.posm_country == 'uae' and ch.posm_customer_id is None]
        if orphaned:
            for ch in orphaned:
                db.session.delete(ch)
            db.session.flush()

        # Build a set of channel keys that already exist
        existing_channel_keys = set()
        for ch in project.posm_channels:
            if ch.posm_country == 'uae':
                existing_channel_keys.add(('uae', ch.posm_customer_id))
            else:
                existing_channel_keys.add((ch.posm_country, None))

        # Create any channels that are missing (new customers / first-time load)
        new_channels_added = False
        for region_key in GULF_REGION_KEYS:
            if region_key not in brief_sections:
                continue
            if region_key == 'uae':
                
                for pc in brief_sections['uae']:
                    if pc.cancelled:
                        continue
                    if ('uae', pc.id) not in existing_channel_keys:
                        db.session.add(ProjectPosmChannel(
                            project_id=project_id,
                            posm_country='uae',
                            posm_customer_id=pc.id,
                            status='in_queue',
                        ))
                        new_channels_added = True
            else:
                if (region_key, None) not in existing_channel_keys:
                    db.session.add(ProjectPosmChannel(
                        project_id=project_id,
                        posm_country=region_key,
                        posm_customer_id=None,
                        status='in_queue',
                    ))
                    new_channels_added = True
        if new_channels_added:
            db.session.commit()

        # Sort channels: UAE first (by customer name), then other regions in Gulf key order
        def _ch_sort_key(ch):
            idx = GULF_REGION_KEYS.index(ch.posm_country) if ch.posm_country in GULF_REGION_KEYS else 99
            cust_name = ch.posm_customer.customer.name if ch.posm_customer else ''
            return (idx, cust_name)

        for channel in sorted(project.posm_channels, key=_ch_sort_key):
            if channel.posm_country == 'uae' and channel.posm_customer:
                label = f'UAE — {channel.posm_customer.customer.name}'
            else:
                label = GULF_REGION_NAMES.get(channel.posm_country, channel.posm_country.title())

            # Active submission for this channel specifically
            ch_sub_q = _PS.query.filter_by(
                project_id=project_id,
                is_active=True,
                posm_country=channel.posm_country,
            )
            if channel.posm_customer_id is not None:
                ch_sub_q = ch_sub_q.filter(_PS.posm_customer_id == channel.posm_customer_id)
            else:
                ch_sub_q = ch_sub_q.filter(_PS.posm_customer_id == None)  # noqa: E711
            ch_active_sub = ch_sub_q.first()

            # Latest revision for this channel
            ch_rev_q = _PR.query.filter_by(
                project_id=project_id,
                posm_country=channel.posm_country,
            )
            if channel.posm_customer_id is not None:
                ch_rev_q = ch_rev_q.filter(_PR.posm_customer_id == channel.posm_customer_id)
            else:
                ch_rev_q = ch_rev_q.filter(_PR.posm_customer_id == None)  # noqa: E711
            ch_latest_rev = ch_rev_q.order_by(_PR.sent_at.desc()).first()

            posm_channels_data.append({
                'channel': channel,
                'label': label,
                'active_submission': ch_active_sub,
                'latest_revision': ch_latest_rev,
                'cancelled': channel.posm_customer.cancelled if channel.posm_customer else False,
            })
    
    from app.models import ProjectSubmission
    pc_ids_with_submissions = {
        s.posm_customer_id
        for s in ProjectSubmission.query.filter_by(project_id=project_id).all()
        if s.posm_customer_id is not None
    }

    return render_template(
        'projects/detail.html',
        project=project,
        designers_by_team=designers_by_team,
        assignments_by_team=assignments_by_team,
        brief_sections=brief_sections,
        assignments_by_deliverable=assignments_by_deliverable,
        open_flags=open_flags,
        all_flags=all_flags,
        standard_deliverables=standard_deliverables,
        standard_assignments_by_deliverable=standard_assignments_by_deliverable,
        standard_designers=standard_designers,
        standard_team=standard_team,
        standard_designers_by_deliverable=standard_designers_by_deliverable,
        active_submission=active_submission,
        past_submissions=past_submissions,
        submitted_history=submitted_history,
        deliverables_json=deliverables_json,
        latest_revision=ProjectRevision.query.filter_by(project_id=project_id)
                        .order_by(ProjectRevision.sent_at.desc()).first(),
        
        secondary_cs_assignments=secondary_cs_assignments,
        is_secondary_cs=is_secondary_cs,
        my_secondary_regions=my_secondary_regions,
        available_cs_users=available_cs_users,
        posm_active=posm_active,
        is_gulf=is_gulf,
        gulf_regions_json=gulf_regions_json,
        gulf_posm_counts=gulf_posm_counts,
        project_customers_json=project_customers_json,
        gulf_region_names=GULF_REGION_NAMES,
        posm_channels_data=posm_channels_data,
        ckv_submission=ckv_submission,
        pc_ids_with_submissions=pc_ids_with_submissions,
        # Latest revision request sent for C&KV specifically.
        # Filtered to posm_country=None so POSM channel revisions don't bleed in.
        # Only queried for CCM briefs — None for all others.
        ckv_latest_revision=(
            ProjectRevision.query.filter_by(
                project_id=project_id,
                posm_country=None,
                posm_customer_id=None
            ).order_by(ProjectRevision.sent_at.desc()).first()
            if project.brief_type == 'ccm' else None
        ),

        # Total revision count across C&KV + all POSM channels for CCM projects.
        # We count ProjectRevision rows directly — each revision (C&KV or channel)
        # gets one row, so the count is always accurate.
        total_revision_count=(
            ProjectRevision.query.filter_by(project_id=project_id).count()
            if project.brief_type == 'ccm' else 0
        ),
    )

@projects.route('/projects/<int:project_id>/update-status', methods=['POST'])
@login_required
@role_required('admin')
def update_status(project_id):
    project = Project.query.get_or_404(project_id)
    new_status = request.form.get('status')

    TIMER_ACTIVE = {'In Progress', 'Revision in Progress'}

    was_active = project.status in TIMER_ACTIVE
    now_active = new_status in TIMER_ACTIVE

    if not was_active and now_active:
        if project.timer_started_at is None and project.hours_accumulated == 0:
            project.design_start_date = datetime.now()
        project.timer_started_at = datetime.now()

    if was_active and not now_active:
        if project.timer_started_at:
            from app.utils import work_hours_between
            project.hours_accumulated += work_hours_between(project.timer_started_at, datetime.now())
            project.timer_started_at = None
    
    project.status = new_status
    db.session.commit()

    flash(f'Project status updated to "{new_status}".', 'success')
    return redirect(url_for('project_detail.detail', project_id=project.id))

@projects.route('/projects/<int:project_id>/set-status', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'designer', 'team_lead')
def set_project_status(project_id):
    from app.utils import log_activity
    project = Project.query.get_or_404(project_id)
    data = request.get_json()
    new_status = data.get('status')

    VALID = ['briefed', 'in_queue', 'in_progress', 'submitted',
             'revision_in_queue', 'revision_in_progress', 'approved', 'on_hold']
    if new_status not in VALID:
        return jsonify({'error': 'Invalid status'}), 400

    old_status = project.project_status
    project.project_status = new_status
    db.session.commit()

    log_activity(
        'project_status_changed',
        f'Project "{project.name}" status changed from "{old_status}" to "{new_status}" by {current_user.name}',
        user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id
    )
    return jsonify({'success': True})  

@projects.route('/projects/<int:project_id>/toggle-hold', methods=['POST'])
@login_required
def toggle_hold(project_id):
    from app.utils import log_activity
    from flask import session as flask_session
    project = Project.query.get_or_404(project_id)

    # Resolve effective user (supports admin emulation)
    emulating_id = flask_session.get('emulating_user_id')
    if emulating_id and current_user.role == 'admin':
        effective_user = User.query.get(emulating_id)
    else:
        effective_user = current_user

    # Only CS lead, secondary CS, or admin
    from app.models import ProjectSecondaryCS
    is_secondary = ProjectSecondaryCS.query.filter_by(
        project_id=project_id, user_id=effective_user.id
    ).first() is not None

    if not (effective_user.role == 'admin' or
            project.cs_lead_id == effective_user.id or
            is_secondary):
        abort(403)

    if project.project_status == 'on_hold':
        # Resume: restore previous status (fall back to briefed)
        restore_to = project.held_from_status or 'briefed'
        project.project_status = restore_to
        project.held_from_status = None
        log_activity('project_resumed', f'Project "{project.name}" resumed (status: {restore_to})',
                     user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)
        flash('Project resumed.', 'success')
    else:
        # Put on hold: save current status first
        project.held_from_status = project.project_status
        project.project_status = 'on_hold'
        log_activity('project_on_hold', f'Project "{project.name}" put on hold',
                     user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)
        flash('Project put on hold.', 'success')

    db.session.commit()
    return redirect(url_for('project_detail.detail', project_id=project_id))


@projects.route('/projects/<int:project_id>/customer/<int:pc_id>/set-status', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'designer', 'team_lead')
def set_customer_status(project_id, pc_id):
    from app.utils import log_activity
    from app.models import ProjectCustomer
    project = Project.query.get_or_404(project_id)
    pc = ProjectCustomer.query.get_or_404(pc_id)
    data = request.get_json()
    new_status = data.get('status')

    VALID = ['briefed', 'in_queue', 'in_progress', 'submitted',
             'revision_in_queue', 'revision_in_progress', 'approved', 'on_hold']
    if new_status not in VALID:
        return jsonify({'error': 'Invalid status'}), 400

    old_status = pc.status
    pc.status = new_status

    # Cascade: approving a customer approves all its deliverables too
    if new_status == 'approved':
        for deliverable in pc.deliverables:
            deliverable.status = 'approved'

    db.session.commit()

    log_activity(
        'customer_status_changed',
        f'Customer "{pc.customer.name}" on "{project.name}" status changed from "{old_status}" to "{new_status}" by {current_user.name}',
        user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id
    )
    return jsonify({'success': True, 'approved': new_status == 'approved'})

@projects.route('/projects/<int:project_id>/customer/<int:pc_id>/remove', methods=['POST'])
@login_required
@role_required('admin','cs','management')
def remove_customer(project_id, pc_id):
    from app.utils import log_activity
    from app.notifications import create_notification
    from app.models import ProjectCustomer, ProjectSubmission, DeliverableAssignment, User as UserModel
    project = Project.query.get_or_404(project_id)
    pc = ProjectCustomer.query.get_or_404(pc_id)

    if project.project_status == 'approved':
        return jsonify({'success': False, 'error': 'Project is approved and locked'}), 403
    
    # Guard: refuse if submissions exist - we use cancel instead
    has_submissions = ProjectSubmission.query.filter_by(posm_customer_id=pc.id).first()
    if has_submissions:
        return jsonify({'success': False, 'error': 'Customer has submissions. Use cancel instead.'}), 400
    
    customer_name = pc.customer.name

    # Collect designers to notify (lead + deliverable assignees), deduplicated
    notify_ids = set()
    if project.lead_designer_id:
        notify_ids.add(project.lead_designer_id)
    for d in pc.deliverables:
        for assignment in DeliverableAssignment.query.filter_by(deliverable_id=d.id).all():
            notify_ids.add(assignment.user_id)
    
    db.session.delete(pc)
    db.session.commit()

    # Notify after commit
    for uid in notify_ids:
        recipient = UserModel.query.get(uid)
        if recipient:
            create_notification(
                recipient=recipient,
                message=f'Customer "{customer_name}" was removed from project "{project.name}".',
                notification_type='customer_removed',
                project=project,
                triggered_by=current_user
            )

    log_activity(
        'customer_removed',
        f'Customer "{customer_name}" removed from "{project.name}" by {current_user.name}',
        user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id

    )
    return jsonify ({'success': True})

@projects.route('/projects/<int:project_id>/customer/<int:pc_id>/cancel', methods=['POST'])
@login_required
@role_required('admin', 'cs')
def cancel_customer(project_id, pc_id):
    from app.utils import log_activity
    from app.notifications import create_notification
    from app.models import ProjectCustomer, DeliverableAssignment, User as UserModel
    project = Project.query.get_or_404(project_id)
    pc = ProjectCustomer.query.get_or_404(pc_id)

    if project.project_status == 'approved':
        return jsonify({'success': False, 'error': 'Project is approved and locked'}), 403

    customer_name = pc.customer.name
    pc.cancelled = True

    # Collect designers to notify (lead + deliverable assignees), deduplicated
    notify_ids = set()
    if project.lead_designer_id:
        notify_ids.add(project.lead_designer_id)
    for d in pc.deliverables:
        for assignment in DeliverableAssignment.query.filter_by(deliverable_id=d.id).all():
            notify_ids.add(assignment.user_id)

    db.session.commit()

    # Notify after commit
    for uid in notify_ids:
        recipient = UserModel.query.get(uid)
        if recipient:
            create_notification(
                recipient=recipient,
                message=f'Customer "{customer_name}" was cancelled on project "{project.name}".',
                notification_type='customer_cancelled',
                project=project,
                triggered_by=current_user
            )

    log_activity(
        'customer_cancelled',
        f'Customer "{customer_name}" cancelled on "{project.name}" by {current_user.name}',
        user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id
    )
    return jsonify({'success': True})


@projects.route('/projects/<int:project_id>/deliverable/<int:d_id>/set-status', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'designer', 'team_lead')
def set_deliverable_status(project_id, d_id):
    from app.utils import log_activity
    from app.models import Deliverable
    project = Project.query.get_or_404(project_id)
    deliverable = Deliverable.query.get_or_404(d_id)
    data = request.get_json()
    new_status = data.get('status')

    # Valid deliverable statuses — includes the new submission flow statuses
    VALID = ['in_queue', 'in_progress', 'submitted',
             'revision_in_queue', 'revision_in_progress', 'approved',
             'internal_review', 'internal_revision', 'submitted_to_client']
    if new_status not in VALID:
        return jsonify({'error': 'Invalid status'}), 400

    from app.models import Deliverable as Del

    old_status = deliverable.status
    deliverable.status = new_status

    revision_completed = False

    # Per-deliverable revision cycle: when a designer re-submits a flagged deliverable
    # and it's the last flagged one, increment per-deliverable revision counts.
    # NOTE: project.revision_count and project_status are no longer changed here —
    # those are now managed exclusively by the client submission flow (submit_to_client).
    if new_status == 'submitted' and deliverable.flagged_for_revision:
        others_pending = Del.query.filter(
            Del.project_id == project_id,
            Del.flagged_for_revision == True,
            Del.id != deliverable.id,
            Del.status != 'submitted'
        ).count()

        if others_pending == 0:
            # Last flagged deliverable re-submitted — clear all revision flags
            all_flagged = Del.query.filter_by(project_id=project_id, flagged_for_revision=True).all()
            for d in all_flagged:
                d.revision_count += 1
                d.flagged_for_revision = False
            revision_completed = True

    db.session.commit()

    log_activity(
        'deliverable_status_changed',
        f'Deliverable "{deliverable.name}" on "{project.name}" status changed from "{old_status}" to "{new_status}" by {current_user.name}',
        user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id
    )

    if revision_completed:
        notify_cs_of_revision_submitted(project, triggered_by=current_user)

    # Notify secondary CS of the status change (C&CM only, region-filtered)
    from app.notifications import notify_secondary_cs_of_deliverable_status
    notify_secondary_cs_of_deliverable_status(deliverable, project, new_status, triggered_by=current_user)

    return jsonify({'success': True, 'revision_completed': revision_completed})

@projects.route('/projects/<int:project_id>/deliverable/<int:d_id>/flag-revision', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def flag_deliverable_revision(project_id, d_id):
    from app.models import Deliverable
    project = Project.query.get_or_404(project_id)
    deliverable = Deliverable.query.get_or_404(d_id)

    deliverable.flagged_for_revision = True
    deliverable.status = 'revision_in_queue'
    project.project_status = 'revision_in_queue'

    db.session.commit()

    notify_designers_of_revision_flag(deliverable, project, triggered_by=current_user)

    log_activity(
        'revision_flagged',
        f'"{deliverable.name}" on "{project.name}" flagged for revision by {current_user.name}',
        user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id
    )

    return jsonify({'success': True})


@projects.route('/projects/<int:project_id>/deliverable/<int:d_id>/assign', methods=['POST'])
@login_required
@role_required('admin', 'designer', 'team_lead')
def assign_deliverable(project_id, d_id):
    from app.models import Deliverable, DeliverableAssignment
    project = Project.query.get_or_404(project_id)
    deliverable = Deliverable.query.get_or_404(d_id)

    designer_id = request.form.get('designer_id')
    team = request.form.get('team')

    if not designer_id or not team:
        return redirect(url_for('project_detail.detail', project_id=project_id))

    designer_id = int(designer_id)
    designer = User.query.get_or_404(designer_id)

    existing = DeliverableAssignment.query.filter_by(
        deliverable_id=d_id,
        team=team
    ).first()

    if existing:
        existing.designer_id = designer_id
        existing.assigned_by_id = current_user.id
        existing.assigned_at = datetime.utcnow()
        action_word = 'reassigned'
    else:
        db.session.add(DeliverableAssignment(
            deliverable_id=d_id,
            designer_id=designer_id,
            team=team,
            assigned_by_id=current_user.id
        ))
        action_word = 'assigned'

    db.session.commit()

    log_activity(
        'deliverable_assigned',
        f'{designer.name} {action_word} to "{deliverable.name}" ({team}) on "{project.name}" by {current_user.name}',
        user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id
    )

    return jsonify({'success': True, 'designer_name': designer.name})


# ── Brief Flag System ────────────────────────────────────────────────────────

@projects.route('/projects/<int:project_id>/flags/create', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'designer', 'team_lead', 'management')  # management can raise flags to escalate issues
def create_flag(project_id):
    from app.models import BriefFlag, BriefFlagMessage, User as UserModel
    project = Project.query.get_or_404(project_id)
    data = request.get_json()

    flag_type = data.get('flag_type')
    deliverable_id = data.get('deliverable_id')
    message_text = (data.get('message') or '').strip()

    if flag_type not in ('project', 'deliverable', 'concept', 'kv') or not message_text:
        return jsonify({'error': 'Invalid data'}), 400

    emulating_id = session.get('emulating_user_id')
    actor = UserModel.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    flag = BriefFlag(
        project_id=project_id,
        deliverable_id=deliverable_id or None,
        flag_type=flag_type,
        created_by_id=actor.id
    )
    db.session.add(flag)
    db.session.flush()

    db.session.add(BriefFlagMessage(
        flag_id=flag.id,
        author_id=actor.id,
        message=message_text
    ))
    db.session.commit()

    notify_cs_of_brief_flag(flag, project, triggered_by=actor)

    log_activity(
        'brief_flag_created',
        f'{actor.name} raised a {flag_type} flag on "{project.name}"',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id
    )

    return jsonify({'success': True})


@projects.route('/projects/<int:project_id>/flags/<int:flag_id>/reply', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'designer', 'team_lead', 'management')  # management can participate in flag threads
def reply_flag(project_id, flag_id):
    from app.models import BriefFlag, BriefFlagMessage, User as UserModel
    project = Project.query.get_or_404(project_id)
    flag = BriefFlag.query.get_or_404(flag_id)

    message_text = (request.form.get('message') or '').strip()
    if not message_text:
        return redirect(url_for('project_detail.detail', project_id=project_id))

    emulating_id = session.get('emulating_user_id')
    actor = UserModel.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    db.session.add(BriefFlagMessage(
        flag_id=flag_id,
        author_id=actor.id,
        message=message_text
    ))
    db.session.commit()

    notify_flag_reply(flag, project, triggered_by=actor)

    log_activity(
        'brief_flag_reply',
        f'{actor.name} replied to a flag on "{project.name}"',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id
    )

    return redirect(url_for('project_detail.detail', project_id=project_id))


@projects.route('/projects/<int:project_id>/flags/<int:flag_id>/resolve', methods=['POST'])
@login_required
@role_required('admin', 'designer', 'team_lead', 'management')  # management can resolve any flag (oversight role)
def resolve_flag(project_id, flag_id):
    from app.models import BriefFlag, User as UserModel
    project = Project.query.get_or_404(project_id)
    flag = BriefFlag.query.get_or_404(flag_id)

    emulating_id = session.get('emulating_user_id')
    actor = UserModel.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    # Only the flag creator, admin, or management can resolve — others (e.g. designers on unrelated flags) cannot
    if flag.created_by_id != actor.id and current_user.role not in ('admin', 'management'):
        return jsonify({'error': 'Only the person who raised this flag can resolve it'}), 403

    flag.is_resolved = True
    flag.resolved_at = datetime.utcnow()
    flag.resolved_by_id = actor.id
    db.session.commit()

    notify_cs_of_flag_resolved(flag, project, triggered_by=actor)

    log_activity(
        'brief_flag_resolved',
        f'{actor.name} resolved a {flag.flag_type} flag on "{project.name}"',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id
    )

    return jsonify({'success': True})


# ── Designer / Team assignment ───────────────────────────────────────────────

@projects.route('/projects/<int:project_id>/assign-designers', methods=['POST'])
@login_required
@role_required('admin', 'team_lead')
def assign_designers(project_id):
    project = Project.query.get_or_404(project_id)

    # Lead designer logic - commented out for MVP, will return in Phase 2
    # lead_designer_id = request.form.get('lead_designer_id')
    # project.lead_designer_id = int(lead_designer_id) if lead_designer_id else None

    requested_teams = [t.strip() for t in project.design_teams_requested.split(',')]

    # Track new assignments so we can fire notifications after commit
    new_assignments = []

    for team in requested_teams:
        field_name = f"designer_{team.lower()}"
        user_id = request.form.get(field_name)

        if not user_id:
            continue  # Skip teams that weren't submitted in this form

        # Team leads can only assign for their own team
        if current_user.role == 'team_lead' and current_user.team != team:
            continue

        designer = User.query.get(int(user_id))
        if not designer:
            continue

        # Remove existing assignment for THIS team only - not all teams
        existing = ProjectDesigner.query.filter_by(
            project_id=project.id,
            team=team
        ).first()
        if existing:
            db.session.delete(existing)

        # Create the new assignment
        assignment = ProjectDesigner(
            project_id=project.id,
            user_id=int(user_id),
            team=team
        )
        db.session.add(assignment)

        new_assignments.append((designer, team))

    db.session.commit()

    # Send notifications for each new assignment - after commit so the data is saved
    for designer, team in new_assignments:
        notify_cs_lead_of_assignment(
            project=project,
            designer=designer,
            team_name=team,
            triggered_by=current_user
        )
        log_activity('designer_assigned', f'{designer.name} assigned to {team} team on "{project.name}"', user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})


@projects.route('/projects/<int:project_id>/assign-lead', methods=['POST'])
@login_required
def assign_lead(project_id):
    project = Project.query.get_or_404(project_id)
    data = request.get_json() or {}
    team = data.get('team', '').strip()
    new_designer_id = data.get('new_designer_id')

    if not team:
        return jsonify({'success': False, 'error': 'Team is required.'}), 400

    # Role guard: designers can only assign for their own team
    actor = current_user
    if actor.role == 'designer' and actor.team != team:
        return jsonify({'success': False, 'error': 'You can only assign yourself to your own team.'}), 403

    # Get current lead for this team (if any)
    current_assignment = ProjectDesigner.query.filter_by(
        project_id=project.id, team=team
    ).first()
    previous_designer = current_assignment.designer if current_assignment else None

    if new_designer_id:
        # Current lead is transferring to a specific person — only the current lead can do this
        if not current_assignment or current_assignment.user_id != actor.id:
            return jsonify({'success': False, 'error': 'Only the current lead can transfer ownership.'}), 403
        new_designer = User.query.get(int(new_designer_id))
        if not new_designer:
            return jsonify({'success': False, 'error': 'Designer not found.'}), 404
        db.session.delete(current_assignment)
        db.session.add(ProjectDesigner(project_id=project.id, user_id=new_designer.id, team=team))
        db.session.commit()
        notify_cs_of_lead_change(project, new_designer, team, triggered_by=actor, previous_designer=previous_designer)
        log_activity('lead_transferred',
                     f'{actor.name} transferred {team} lead to {new_designer.name} on "{project.name}"',
                     user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    else:
        # Self-assign or immediate takeover
        if current_assignment:
            db.session.delete(current_assignment)
        db.session.add(ProjectDesigner(project_id=project.id, user_id=actor.id, team=team))
        db.session.commit()
        notify_cs_of_lead_change(project, actor, team, triggered_by=actor, previous_designer=previous_designer)
        action = 'lead_transferred' if previous_designer else 'lead_assigned'
        description = (
            f'{actor.name} took over as {team} lead on "{project.name}" '
            f'(previously {previous_designer.name})'
            if previous_designer
            else f'{actor.name} self-assigned as {team} lead on "{project.name}"'
        )
        log_activity(action, description, user=actor,
                     entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})

# _____________ Auto-generate FOC Job Number __________
# Returns the next available FOC-NNN job number.
# FOC_PAD controls zero-padding width - change to 4 to get FOC-1000 etc.
@projects.route('/projects/generate-job-number', methods=['GET'])
@login_required
@role_required('admin', 'cs', 'management')
def generate_job_number():
    FOC_PAD = 3 # Digits: 3 -> FOC-001 ... FOC-999. Change to 4 for FOC-1000+

    #Pull all existing FOC job numbers from the DB
    existing = Project.query.with_entities(Project.job_number).filter(
        Project.job_number.like('FOC-%')
    ).all()

    # Parse the numeric suffix from each, collect into a list
    used_numbers = []
    for (jn,) in existing:
        suffix = jn[4:] # strip 'FOC- prefix
        if suffix.isdigit():
            used_numbers.append(int(suffix))
    
    # Next number is max +1, or 1 if none exist yet
    next_num = (max(used_numbers) + 1) if used_numbers else 1
    job_number = 'FOC-' + str(next_num).zfill(FOC_PAD)

    return jsonify({'job_number': job_number})

# _____________ Start Project ________________________
# Transitions project_status from Briefed to In Progress.
# Accessible to designers who team is requested on the project, and admins.
# Guard against double start: if aleady past Briefed stage, return an error.
@projects.route('/projects/<int:project_id>/start-project', methods=['POST'])
@login_required
def start_project(project_id):
    project = Project.query.get_or_404(project_id)

    # Resolve the effective actor to respect admin emulation
    emulating_id = session.get('emulating_user_id')
    actor = User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    # Role guard: must be an admin, designer, or team lead whose team is requested on this project
    requested_teams = [t.strip() for t in (project.design_teams_requested or '').split(',')]
    if actor.role != 'admin' and not (actor.role in ('designer', 'team_lead') and actor.team in requested_teams):
        return jsonify({'success': False, 'error': 'You are not assigned to a team requested on this project.'}), 400

    # Idempotency guard: only move forward if currently briefed
    if project.project_status != 'briefed':
        return jsonify({'success': False, 'error': 'Project is not in Briefed status.'}), 400

    # Transition status
    project.project_status = 'in_progress'

    # Auto-assign the actor as lead for their team
    if actor.team:
        existing = ProjectDesigner.query.filter_by(project_id=project.id, team=actor.team).first()
        if existing:
            db.session.delete(existing)
            db.session.flush()
        db.session.add(ProjectDesigner(project_id=project.id, user_id=actor.id, team=actor.team))

    db.session.commit()

    # Notify CS lead, secondary CS, and other assigned lead designers
    notify_cs_of_project_started(project, triggered_by=actor)
    notify_lead_designers_of_project_started(project, triggered_by=actor)

    # Record in activity log
    log_activity('project_started',
                 f'{actor.name} started work on "{project.name}"',
                 user=actor, entity_type='project',
                 entity_name=project.name, entity_id=project.id)
    
    return jsonify({'success': True})




@projects.route('/projects/<int:project_id>/secondary-cs', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def add_secondary_cs(project_id):
    """Add a CS user as secondary CS on a project. Only the CS lead or admin can do this."""
    from app.models import ProjectSecondaryCS
    project = Project.query.get_or_404(project_id)

    if current_user.role != 'admin' and current_user.id != project.cs_lead_id:
        abort(403)

    user_id = request.form.get('user_id', type=int)
    if not user_id:
        return jsonify({'success': False, 'error': 'Please select a CS member.'}), 400

    if user_id == project.cs_lead_id:
        return jsonify({'success': False, 'error': 'The CS lead is already the primary CS on this project.'}), 400

    user = User.query.get_or_404(user_id)
    if user.role != 'cs':
        return jsonify({'success': False, 'error': 'Only CS members can be added as secondary CS.'}), 400

    if ProjectSecondaryCS.query.filter_by(project_id=project_id, user_id=user_id).first():
        return jsonify({'success': False, 'error': 'Already a secondary CS on this project.'}), 400

    db.session.add(ProjectSecondaryCS(project_id=project_id, user_id=user_id, added_by_id=current_user.id))
    db.session.commit()

    log_activity('secondary_cs_added', f'{user.name} added as secondary CS on "{project.name}"',
                 user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)
    return jsonify({'success': True})


@projects.route('/projects/<int:project_id>/secondary-cs/<int:user_id>/remove', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def remove_secondary_cs(project_id, user_id):
    """Remove a secondary CS from a project."""
    from app.models import ProjectSecondaryCS, ProjectSecondaryCsRegion
    project = Project.query.get_or_404(project_id)

    if current_user.role != 'admin' and current_user.id != project.cs_lead_id:
        abort(403)

    assignment = ProjectSecondaryCS.query.filter_by(project_id=project_id, user_id=user_id).first_or_404()
    user = User.query.get(user_id)

    # Clean up their region subscriptions too
    ProjectSecondaryCsRegion.query.filter_by(project_id=project_id, user_id=user_id).delete()
    db.session.delete(assignment)
    db.session.commit()

    log_activity('secondary_cs_removed', f'{user.name} removed as secondary CS on "{project.name}"',
                 user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)
    return jsonify({'success': True})


@projects.route('/projects/<int:project_id>/secondary-cs/regions', methods=['POST'])
@login_required
def update_secondary_cs_regions(project_id):
    """Update C&CM region notification subscriptions for the current secondary CS."""
    from flask import session as flask_session
    from app.models import ProjectSecondaryCS, ProjectSecondaryCsRegion
    project = Project.query.get_or_404(project_id)

    # Resolve effective user (admin emulation)
    emulating_id = flask_session.get('emulating_user_id')
    if emulating_id and current_user.role == 'admin':
        effective_user = User.query.get(emulating_id)
    else:
        effective_user = current_user

    # Must be a secondary CS on this project
    if not ProjectSecondaryCS.query.filter_by(project_id=project_id, user_id=effective_user.id).first():
        abort(403)

    selected_regions = set(request.form.getlist('regions'))
    valid_regions = {'uae', 'kuwait', 'qatar', 'bahrain', 'oman'}

    ProjectSecondaryCsRegion.query.filter_by(project_id=project_id, user_id=effective_user.id).delete()
    for region in selected_regions & valid_regions:
        db.session.add(ProjectSecondaryCsRegion(project_id=project_id, user_id=effective_user.id, region=region))

    db.session.commit()
    flash('Region notification preferences updated.', 'success')
    return redirect(url_for('project_detail.detail', project_id=project_id))


@projects.route('/projects/<int:project_id>/assign-concept-kv', methods=['POST'])
@login_required
@role_required('admin', 'team_lead', 'cs', 'designer')
def assign_concept_kv(project_id):
    project = Project.query.get_or_404(project_id)

    concept_id = request.form.get('concept_designer_id')
    kv_id = request.form.get('kv_designer_id')

    # Designers can only assign themselves — block any attempt to assign someone else
    if current_user.role == 'designer':
        if concept_id and int(concept_id) != current_user.id:
            abort(403)
        if kv_id and int(kv_id) != current_user.id:
            abort(403)

    if concept_id:
        project.concept_designer_id = int(concept_id)
    if kv_id:
        project.kv_designer_id = int(kv_id)

    db.session.commit()
    if concept_id:
        concept_designer = User.query.get(int(concept_id))
        if concept_designer:
            notify_designer_of_concept_kv_assignment(project, concept_designer, 'Concept', triggered_by=current_user)
            log_activity('designer_assigned', f'{concept_designer.name} assigned as Concept designer on "{project.name}"', user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)
    if kv_id:
        kv_designer = User.query.get(int(kv_id))
        if kv_designer:
            notify_designer_of_concept_kv_assignment(project, kv_designer, 'Key Visual', triggered_by=current_user)
            log_activity('designer_assigned', f'{kv_designer.name} assigned as KV designer on "{project.name}"', user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)
    return redirect(url_for('project_detail.detail', project_id=project.id))

@projects.route('/projects/<int:project_id>/download-brief')
@login_required
def download_brief(project_id):
    project = Project.query.get_or_404(project_id)
    return send_from_directory(
        current_app.config['UPLOAD_FOLDER'],
        project.brief_file,
        as_attachment=True
    )

@projects.route('/<int:project_id>/delete', methods=['POST'])
@login_required
def delete_project(project_id):
    from app.models import ProjectFile

    # Use effective_user so emulation mode respects the underlying admin session
    effective_user = User.query.get(session['emulating_user_id']) if session.get('emulating_user_id') else current_user

    project = Project.query.get_or_404(project_id)

    if effective_user.role != 'admin' and project.cs_lead_id != effective_user.id:
        flash('You do not have permission to delete this project.', 'error')
        return redirect(url_for('project_detail.detail', project_id=project.id))

    # Remove any uploaded reference files from disk before deleting the project row.
    # The SQLAlchemy cascade handles the DB records; this handles the physical files.
    upload_folder = current_app.config['UPLOAD_FOLDER']
    for ref_file in project.reference_files:
        file_path = os.path.join(upload_folder, ref_file.filename)
        if os.path.exists(file_path):
            os.remove(file_path)

    project_name = project.name
    db.session.delete(project)
    db.session.commit()
    flash(f'Project "{project_name}" has been deleted.', 'success')
    return redirect(url_for('main.index'))


@projects.route('/projects/drafts')
@login_required
@role_required('admin', 'cs', 'management')
def drafts():
    user_drafts = Project.query.filter_by(
        created_by_id=current_user.id,
        project_status='draft'
    ).order_by(Project.last_autosaved_at.desc()).all()

    if not user_drafts:
        return redirect(url_for('brief.create'))

    return render_template('projects/drafts.html', drafts=user_drafts)


@projects.route('/projects/drafts/<int:draft_id>/delete', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def delete_draft(draft_id):
    draft = Project.query.get_or_404(draft_id)

    if draft.created_by_id != current_user.id:
        return jsonify({'success': False, 'error': 'Unauthorised'}), 403

    if draft.project_status != 'draft':
        return jsonify({'success': False, 'error': 'This project is not a draft'}), 400

    db.session.delete(draft)
    db.session.commit()

    return jsonify({'success': True})

@projects.route('/projects/deliverable-types/<int:customer_id>')
@login_required
def get_deliverable_types(customer_id):
    client_id = request.args.get('client_id', type=int)

    types = DeliverableType.query.filter_by(
        customer_id=customer_id,
        client_id=client_id,
        is_active=True
    ).order_by(DeliverableType.name).all()

    return jsonify([{
        'id': dt.id,
        'name': dt.name,
        'disciplines': [d.team for d in dt.disciplines],
        'is_custom': dt.is_custom
    } for dt in types])


@projects.route('/clients/add', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def add_client():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'success': False, 'error': 'Client name is required'}), 400

    try:
        name = data['name'].strip()

        existing = Client.query.filter_by(name=name).first()
        if existing:
            return jsonify({'success': False, 'error': 'A client with this name already exists'}), 400

        client = Client(name=name, created_by=current_user)
        db.session.add(client)
        db.session.commit()

        return jsonify({
            'success': True,
            'client': {'id': client.id, 'name': client.name}
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Add client failed: {str(e)}')
        return jsonify({'success': False, 'error': 'Something went wrong. Please try again.'}), 500
    
@projects.route('/projects/deliverable-types/add', methods=['POST'])
@login_required
@role_required('cs', 'admin', 'management')
def add_deliverable_type():
    try:
        data = request.get_json()

        name = data.get('name', '').strip()
        client_id = data.get('client_id')
        customer_id = data.get('customer_id')
        disciplines = data.get('disciplines', [])

        if not name:
            return jsonify({'error': 'Deliverable name is required.'}), 400

        if not disciplines:
            return jsonify({'error': 'At least one discipline is required.'}), 400

        if not client_id or not customer_id:
            return jsonify({'error': 'Client and customer are required.'}), 400

        existing = DeliverableType.query.filter_by(
            name=name,
            client_id=client_id,
            customer_id=customer_id
        ).first()

        if existing:
            return jsonify({'error': 'A deliverable called "' + name + '" already exists for this customer.'}), 409

        new_type = DeliverableType(
            name=name,
            client_id=client_id,
            customer_id=customer_id,
            is_active=True,
            is_custom=True
        )
        db.session.add(new_type)
        db.session.flush()

        for team in disciplines:
            discipline = DeliverableTypeDiscipline(
                deliverable_type_id=new_type.id,
                team=team
            )
            db.session.add(discipline)

        db.session.commit()
        log_activity('deliverable_created', f'Custom deliverable type "{new_type.name}" created', user=current_user, entity_type='deliverable', entity_name=new_type.name, entity_id=new_type.id)

        return jsonify({
            'id': new_type.id,
            'name': new_type.name,
            'disciplines': disciplines,
            'is_custom': True
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Something went wrong. Please try again.'}), 500
    

@projects.route('/projects/submit', methods=['POST'])
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

        project.name = data['name']
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
        project.project_status = 'briefed'
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

        db.session.commit()

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

@projects.route('/projects/<int:project_id>/standard-deliverables/add', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'designer', 'team_lead')
def add_standard_deliverable(project_id):
    project = Project.query.get_or_404(project_id)
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Deliverable name is required'}), 400

    from datetime import date as date_type
    def parse_date(val):
        if not val:
            return None
        try:
            from datetime import datetime
            return datetime.strptime(val, '%Y-%m-%d').date()
        except ValueError:
            return None

    deliverable = Deliverable(
        project_id=project_id,
        project_customer_id=None,
        deliverable_type_id=None,
        name=name,
        design_deadline=parse_date(data.get('design_deadline')),
        installation_deadline=parse_date(data.get('installation_deadline')),
        status='in_queue',
        created_by=current_user
    )
    db.session.add(deliverable)
    db.session.commit()

    log_activity('deliverable_created', f'Standard deliverable "{name}" added to "{project.name}"',
                 user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({
        'id': deliverable.id,
        'name': deliverable.name,
        'status': deliverable.status,
        'design_deadline': deliverable.design_deadline.isoformat() if deliverable.design_deadline else None,
        'installation_deadline': deliverable.installation_deadline.isoformat() if deliverable.installation_deadline else None,
    })


@projects.route('/projects/<int:project_id>/standard-deliverables/<int:d_id>/delete', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def delete_standard_deliverable(project_id, d_id):
    deliverable = Deliverable.query.filter_by(id=d_id, project_id=project_id).first_or_404()
    name = deliverable.name
    project = Project.query.get_or_404(project_id)
    db.session.delete(deliverable)
    db.session.commit()
    log_activity('deliverable_deleted', f'Standard deliverable "{name}" removed from "{project.name}"',
                 user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)
    return jsonify({'success': True})


@projects.route('/projects/<int:project_id>/standard-deliverables/<int:d_id>/assign', methods=['POST'])
@login_required
@role_required('admin', 'designer', 'team_lead')
def assign_standard_deliverable(project_id, d_id):
    from app.models import DeliverableAssignment
    project = Project.query.get_or_404(project_id)
    deliverable = Deliverable.query.filter_by(id=d_id, project_id=project_id).first_or_404()

    designer_id = request.form.get('designer_id')
    if not designer_id:
        return jsonify({'success': False, 'error': 'Missing designer'}), 400

    designer_id = int(designer_id)
    designer = User.query.get_or_404(designer_id)
    team = designer.team or 'General'

    # For standard brief deliverables, one assignment per deliverable (replace any existing)
    existing = DeliverableAssignment.query.filter_by(deliverable_id=d_id).first()
    if existing:
        existing.designer_id = designer_id
        existing.team = team
        existing.assigned_by_id = current_user.id
        existing.assigned_at = datetime.utcnow()
    else:
        db.session.add(DeliverableAssignment(
            deliverable_id=d_id,
            designer_id=designer_id,
            team=team,
            assigned_by_id=current_user.id
        ))

    db.session.commit()
    log_activity('deliverable_assigned',
                 f'{designer.name} assigned to "{deliverable.name}" on "{project.name}"',
                 user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)
    return jsonify({'success': True, 'designer_name': designer.name})

import uuid

@projects.route('/projects/<int:project_id>/upload-file', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def upload_project_file(project_id):
    """Handle reference file uploads for a project. CS and admin only."""
    from app.models import ProjectFile
    import os

    project = Project.query.get_or_404(project_id)

    # Check a file was actually included in the request
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    # Only allow safe file types
    allowed_extensions = {'jpg', 'jpeg', 'png', 'pdf', 'docx', 'xlsx', 'pptx'}
    original_filename = file.filename
    ext = original_filename.rsplit('.', 1)[-1].lower() if '.' in original_filename else ''

    if ext not in allowed_extensions:
        return jsonify({'success': False, 'error': f'File type .{ext} not allowed'}), 400

    # Generate a unique filename to avoid collisions on disk
    stored_filename = f"{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], stored_filename)
    file.save(save_path)

    # Save the record to the database
    project_file = ProjectFile(
        project_id=project_id,
        filename=stored_filename,
        original_filename=original_filename,
        file_type=ext,
        uploaded_by_id=current_user.id
    )
    db.session.add(project_file)
    db.session.commit()

    # Mirror the file to the NAS under Reference Files/
    from app.nas import upload_file_to_nas
    upload_file_to_nas(project, 'Reference Files', save_path, original_filename)

    log_activity('file_uploaded', f'Reference file "{original_filename}" uploaded to "{project.name}"',
                 user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({
        'success': True,
        'file': {
            'id': project_file.id,
            'original_filename': original_filename,
            'file_type': ext,
            'uploaded_by': current_user.name
        }
    })


@projects.route('/projects/files/<int:file_id>/download')
@login_required
def download_project_file(file_id):
    """Serve a reference file for download. All authenticated users can download."""
    from app.models import ProjectFile
    import os

    project_file = ProjectFile.query.get_or_404(file_id)
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], project_file.filename)

    if not os.path.exists(file_path):
        abort(404)

    # send_file serves the file to the browser with the original filename
    from flask import send_file
    return send_file(file_path, as_attachment=True, download_name=project_file.original_filename)


@projects.route('/projects/files/<int:file_id>/delete', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def delete_project_file(file_id):
    """Delete a reference file. CS and admin only."""
    from app.models import ProjectFile
    import os

    project_file = ProjectFile.query.get_or_404(file_id)
    project = Project.query.get(project_file.project_id)

    # Remove the file from disk
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], project_file.filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    log_activity('file_deleted', f'Reference file "{project_file.original_filename}" deleted from "{project.name}"',
                 user=current_user, entity_type='project', entity_name=project.name, entity_id=project.id)

    db.session.delete(project_file)
    db.session.commit()

    return jsonify({'success': True})

# ── Project Submission Routes ─────────────────────────────────────────────────
# Flow:
#   1. Designer uploads deck → upload_submission (returns submission.id + previous deliverable IDs)
#   2. Designer picks deliverables → submit_for_internal_review (project + deliverables → internal_review)
#   3. CS reviews:
#      a. Flags it  → flag_submission (project + deliverables → internal_revision, notify designer)
#         Designer reuploads (repeat from step 1), new submission inherits previous picker selection
#      b. Approves  → submit_to_client (project + ALL deliverables → submitted_to_client,
#                                        revision_count +1, open mailto in browser)
#   Deck files that reached "submitted_to_client" are kept permanently for audit history.
#   Draft/flagged decks that are replaced on reupload are deleted from disk.

@projects.route('/projects/<int:project_id>/submission/upload', methods=['POST'])
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

    # ── Lock guard: approved projects are read-only ──────────────────────────
    if project.project_status == 'approved':
        return jsonify({'success': False, 'error': 'This project has been approved and is locked.'}), 403

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

    upload_folder = current_app.config['UPLOAD_FOLDER']

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
        if not previous.submitted_to_client_at:
            old_path = os.path.join(upload_folder, previous.filename)
            if os.path.exists(old_path):
                os.remove(old_path)
        previous.is_active = False

    # Save the new file with a UUID-based name to prevent filename collisions
    stored_filename = f"submission_{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(upload_folder, stored_filename))

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
        if country == 'uae' and channel.posm_customer_id:
            from app.models import ProjectCustomer as _PC
            pc = _PC.query.get(channel.posm_customer_id)
            posm_rev = (pc.posm_revision_count or 0) if pc else 0
            posm_label = 'Initial' if posm_rev == 0 else f'Revision {posm_rev}'
            customer_name = pc.customer.name if (pc and pc.customer) else 'Customer'
            submission.original_filename = (
                f'{_sanitize(client_name)} - {_sanitize(project.name)} - '
                f'UAE - {_sanitize(customer_name)} - POSM - {posm_label}.{ext}'
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
        project.project_status = 'in_progress'
    elif not channel and project.concept_status in ('revision_in_queue', 'revision_in_progress', 'internal_revision'):
        # C&KV reupload after client revision or internal flag — reset so picker shows
        project.concept_status = 'in_progress'
        if project.kv_status in ('revision_in_queue', 'revision_in_progress', 'internal_revision'):
            project.kv_status = 'in_progress'

    db.session.commit()

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


@projects.route('/projects/<int:project_id>/submission/submit-for-review', methods=['POST'])
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

    # ── Lock guard: approved projects are read-only ──────────────────────────
    if project.project_status == 'approved':
        return jsonify({'success': False, 'error': 'This project has been approved and is locked.'}), 403

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
        project.project_status = 'internal_review'
    else:
        submission.phase = 'concept_kv'
        submission.posm_country    = None
        submission.posm_customer_id = None
        # When the project has POSM channels, project status is driven by those channels.
        # C&KV is a parallel channel — don't overwrite project status here.
        if not project.posm_channels:
            project.project_status = 'internal_review'

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
            deliverable.status = 'internal_review'

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


@projects.route('/projects/<int:project_id>/submission/flag', methods=['POST'])
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

    # ── Lock guard: approved projects are read-only ──────────────────────────
    if project.project_status == 'approved':
        return jsonify({'success': False, 'error': 'This project has been approved and is locked.'}), 403

    data = request.get_json() or {}
    message = (data.get('message') or '').strip()
    posm_channel_id = data.get('posm_channel_id')
    if not message:
        return jsonify({'success': False, 'error': 'Please provide a reason for flagging'}), 400

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
                link.deliverable.status = 'internal_revision'
    else:
        # Push project into internal_revision state
        project.project_status = 'internal_revision'
        # Push every included deliverable into internal_revision
        for link in submission.included_deliverables:
            if link.deliverable:
                link.deliverable.status = 'internal_revision'
        # Push concept/KV too if they were included in this submission
        if submission.includes_concept:
            project.concept_status = 'internal_revision'
        if submission.includes_kv:
            project.kv_status = 'internal_revision'

    db.session.commit()

    # Notify the designer who uploaded the deck
    create_notification(
        recipient=submission.uploaded_by,
        message=f'Your client deck for "{project.name}" was flagged by CS: {message}',
        notification_type='submission_flagged',
        project=project,
        triggered_by=current_user
    )

    log_activity('submission_flagged',
                 f'Client deck for "{project.name}" flagged by {current_user.name}: {message}',
                 user=current_user, entity_type='project',
                 entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})


@projects.route('/projects/<int:project_id>/submission/submit-to-client', methods=['POST'])
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

    # ── Lock guard: approved projects are read-only ──────────────────────────
    if project.project_status == 'approved':
        return jsonify({'success': False, 'error': 'This project has been approved and is locked.'}), 403

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
                link.deliverable.status = 'submitted_to_client'
    else:
        # NOTE: project.revision_count is NOT incremented here.
        # It is incremented only when CS sends a revision back (send_revision route).
        project.project_status = 'submitted_to_client'
        is_revised_submission = (project.revision_count or 0) > 0

        # Standard briefs only: mark deliverables as submitted to client.
        # C&CM concept/KV submissions must not touch deliverables — they remain 'briefed'
        # until the POSM stage begins and the POSM channel flow takes over.
        if project.brief_type != 'ccm':
            for deliverable in project.project_deliverables:
                deliverable.status = 'submitted_to_client'

            # Increment revision_count on each *included* deliverable for revised submissions
            if is_revised_submission:
                included_ids = {link.deliverable_id for link in submission.included_deliverables if link.deliverable_id}
                for deliverable in project.project_deliverables:
                    if deliverable.id in included_ids:
                        deliverable.revision_count = (deliverable.revision_count or 0) + 1

        # Advance concept/KV if they have an active status (i.e. were part of the workflow)
        if project.concept_status:
            project.concept_status = 'submitted_to_client'
        if project.kv_status:
            project.kv_status = 'submitted_to_client'

    db.session.commit()

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


@projects.route('/projects/submission/<int:submission_id>/download')
@login_required
def download_submission(submission_id):
    """Serve a submission deck for download. Available to all authenticated users."""
    from app.models import ProjectSubmission
    import os
    submission = ProjectSubmission.query.get_or_404(submission_id)
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], submission.filename)
    if not os.path.exists(file_path):
        abort(404)
    from flask import send_file
    return send_file(file_path, as_attachment=True, download_name=submission.original_filename)


@projects.route('/projects/<int:project_id>/submission/send-revision', methods=['POST'])
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

    # ── Lock guard: approved projects are read-only ──────────────────────────
    if project.project_status == 'approved':
        return jsonify({'success': False, 'error': 'This project has been approved and is locked.'}), 403

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
                     f'C&KV Revision #{project.ckv_revision_count} sent for "{project.name}" by {current_user.name}: {message[:100]}',
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
    if channel and channel.posm_country == 'uae' and channel.posm_customer_id:
        from app.models import ProjectCustomer
        posm_pc = ProjectCustomer.query.get(channel.posm_customer_id)
    elif not channel and posm_country == 'uae' and posm_customer_id:
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
                        link.deliverable.status = 'revision_in_queue'
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
                deliverable.status = 'revision_in_queue'

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

        project.project_status = 'revision_in_queue'

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
                 f'Revision {rev_label} sent for "{project.name}" by {current_user.name}: {message[:100]}',
                 user=current_user, entity_type='project',
                 entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})


@projects.route('/projects/<int:project_id>/submission/start-revision', methods=['POST'])
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

    # ── Lock guard: approved projects are read-only ──────────────────────────
    if project.project_status == 'approved':
        return jsonify({'success': False, 'error': 'This project has been approved and is locked.'}), 403

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
                    link.deliverable.status = 'revision_in_progress'
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
                link.deliverable.status = 'revision_in_progress'

        project.project_status = 'revision_in_progress'

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


# ── Approval Route ─────────────────────────────────────────────────────────────

@projects.route('/projects/<int:project_id>/submission/approve', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def approve_submission(project_id):
    """CS approves the final client submission, locking the project.

    Standard brief (no posm_channel_id in body):
      - Sets project.project_status to 'approved'
      - All deliverables set to 'approved'
      - concept_status / kv_status set to 'approved' (if set)
      - Stamps project.approved_at / project.approved_by_id

    POSM brief (posm_channel_id provided in body):
      - channel.status set to 'approved'
      - All deliverables included in the channel's latest submission set to 'approved'
      - Stamps channel.approved_at / channel.approved_by_id
      - If ALL channels on the project are now approved:
          project.project_status set to 'approved'
          Stamps project.approved_at / project.approved_by_id

    Expects optional JSON body: { "posm_channel_id": <int> }
    No body (or no posm_channel_id key) => Standard approval path.
    Confirmation popup is handled client-side; this route executes the action."""
    from datetime import datetime as dt
    from app.models import ProjectPosmChannel, ProjectSubmission

    project = Project.query.get_or_404(project_id)
    data = request.get_json(silent=True) or {}
    posm_channel_id = data.get('posm_channel_id')

    now = dt.utcnow()

    if posm_channel_id:
        # ── POSM channel approval path ──────────────────────────────────────
        channel = ProjectPosmChannel.query.filter_by(
            id=int(posm_channel_id), project_id=project_id
        ).first()
        if not channel:
            return jsonify({'success': False, 'error': 'Channel not found'}), 404
        if channel.status == 'approved':
            return jsonify({'success': False, 'error': 'This channel is already approved'}), 400
        if channel.status != 'submitted_to_client':
            return jsonify({'success': False,
                            'error': 'Channel must be in Submitted to Client state to approve'}), 400

        # Approve the channel and stamp who/when
        channel.status = 'approved'
        channel.approved_at = now
        channel.approved_by_id = current_user.id

        # Mark every deliverable that was included in this channel's latest active
        # submission as approved. Scope to the channel's country + customer.
        ch_sub_q = ProjectSubmission.query.filter_by(
            project_id=project_id,
            is_active=True,
            posm_country=channel.posm_country,
        )
        if channel.posm_customer_id is not None:
            ch_sub_q = ch_sub_q.filter(
                ProjectSubmission.posm_customer_id == channel.posm_customer_id
            )
        else:
            ch_sub_q = ch_sub_q.filter(
                ProjectSubmission.posm_customer_id == None  # noqa: E711
            )
        ch_sub = ch_sub_q.first()

        if ch_sub:
            for link in ch_sub.included_deliverables:
                if link.deliverable:
                    link.deliverable.status = 'approved'

        # Check whether ALL channels on this project are now approved.
        # If so, also require C&KV to be approved (if this project has concept/KV).
        # Only then cascade to project-level approval.
        all_channels = ProjectPosmChannel.query.filter_by(project_id=project_id).all()
        if all_channels and all(c.status == 'approved' for c in all_channels):
            ckv_gate = True
            if project.has_concept and project.concept_status != 'approved':
                ckv_gate = False
            if project.has_kv and project.kv_status != 'approved':
                ckv_gate = False
            if ckv_gate:
                project.project_status = 'approved'
                project.approved_at = now
                project.approved_by_id = current_user.id

    else:
        # ── Standard (non-POSM) approval path ──────────────────────────────
        if project.project_status == 'approved':
            return jsonify({'success': False, 'error': 'This project is already approved'}), 400
        if project.project_status != 'submitted_to_client':
            return jsonify({'success': False,
                            'error': 'Project must be in Submitted to Client state to approve'}), 400

        project.project_status = 'approved'
        project.approved_at = now
        project.approved_by_id = current_user.id

        # Mark every deliverable on this project as approved
        for deliverable in project.project_deliverables:
            deliverable.status = 'approved'

        # Advance concept/KV statuses if they were part of the workflow
        if project.concept_status:
            project.concept_status = 'approved'
        if project.kv_status:
            project.kv_status = 'approved'

    db.session.commit()

    log_activity(
        'project_approved',
        f'"{project.name}" approved by {current_user.name}',
        user=current_user, entity_type='project',
        entity_name=project.name, entity_id=project.id
    )

    # Only fire the approval notification when the project itself is fully approved.
    # For POSM flows, individual channel approvals may not yet cascade to the project —
    # so we check project_status after the commit rather than firing unconditionally.
    if project.project_status == 'approved':
        notify_of_project_approved(project, triggered_by=current_user)

    return jsonify({'success': True})


@projects.route('/projects/<int:project_id>/concept-kv/approve', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def approve_concept_kv(project_id):
    """Approve the Concept & KV channel independently during a POSM-parallel project.

    Sets concept_status and kv_status to 'approved', then checks whether all
    POSM channels are also approved — if so, cascades to project-level approval."""
    from datetime import datetime as dt
    from app.models import ProjectPosmChannel
    from app.utils import log_activity

    project = Project.query.get_or_404(project_id)

    if not project.posm_channels:
        return jsonify({'success': False, 'error': 'Concept & KV is only approved independently on projects with POSM channels'}), 400

    if (not project.has_concept and not project.has_kv):
        return jsonify({'success': False, 'error': 'This project has no Concept or KV'}), 400

    if project.concept_status == 'approved' and project.kv_status == 'approved':
        return jsonify({'success': False, 'error': 'Concept & KV is already approved'}), 400

    now = dt.utcnow()

    if project.has_concept:
        project.concept_status = 'approved'
    if project.has_kv:
        project.kv_status = 'approved'

    # Cascade: if all POSM channels are also approved, approve the whole project
    all_channels = ProjectPosmChannel.query.filter_by(project_id=project_id).all()
    if all_channels and all(c.status == 'approved' for c in all_channels):
        project.project_status = 'approved'
        project.approved_at = now
        project.approved_by_id = current_user.id

    db.session.commit()

    log_activity(
        'concept_kv_approved',
        f'Concept & KV approved for "{project.name}" by {current_user.name}',
        user=current_user, entity_type='project',
        entity_name=project.name, entity_id=project.id
    )

    return jsonify({'success': True})
