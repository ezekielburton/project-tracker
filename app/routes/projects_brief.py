import os
import re
import uuid
from datetime import date, datetime
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, current_app, send_from_directory, jsonify, abort, session)
import flask
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import (Project, ProjectDesigner, Scope, User, Client,
                        Customer, DeliverableType, DeliverableTypeDiscipline,
                        ProjectRegion, ProjectCustomer, Deliverable,
                        DeliverableAssignment, DesignType, DesignDirection,
                        ProjectSubmission)
from app.decorators import role_required
from app.notifications import (
    notify_team_leads_of_new_project, notify_cs_lead_of_assignment,
    notify_cs_of_lead_change
)
from app.utils import log_activity
from app.status_tracking import record_project_status, record_customer_status, record_deliverable_status

brief_bp = Blueprint('brief', __name__)

@brief_bp.route('/projects/create', methods=['GET'])
@login_required
@role_required('admin', 'cs', 'management')
def create():
    cs_users = User.query.filter(
        User.role.in_(['cs', 'admin', 'management'])
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

@brief_bp.route('/projects/<int:project_id>/edit', methods=['GET'])
@login_required
@role_required('admin', 'cs', 'management')
def edit_project(project_id):
    project = Project.query.get_or_404(project_id)

    # Secondary CS get the same edit rights as the CS lead — imported locally
    # here (not at module top) to avoid circular imports, matching the pattern
    # used for activity logging elsewhere in the app.
    from app.models import ProjectSecondaryCS
    is_secondary_cs = ProjectSecondaryCS.query.filter_by(
        project_id=project_id, user_id=current_user.id
    ).first() is not None

    if current_user.role == 'cs' and project.cs_lead_id != current_user.id and not is_secondary_cs:
        abort(403)

    cs_users = User.query.filter(User.role.in_(['cs', 'admin', 'management'])).order_by(User.name).all()
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


@brief_bp.route('/projects/<int:project_id>/update', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def update_project(project_id):
    project = Project.query.get_or_404(project_id)

    from app.models import ProjectSecondaryCS
    is_secondary_cs = ProjectSecondaryCS.query.filter_by(
        project_id=project_id, user_id=current_user.id
    ).first() is not None

    if current_user.role == 'cs' and project.cs_lead_id != current_user.id and not is_secondary_cs:
        abort(403)

    # Emulation-aware actor — resolved here (rather than down near the
    # notification code, where it used to live) since the customer/deliverable
    # upsert logic below now needs it for record_customer_status() /
    # record_deliverable_status() calls.
    emulating_id = flask.session.get('emulating_user_id')
    actor = User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    # Snapshot taken BEFORE any mutation below — used after the customer
    # upsert to detect "this edit is the one that came out of Pause" (see
    # notify_of_posm_details_added call further down). Both conditions have
    # to be true of the state as it was walking in the door, not after.
    was_awaiting_posm_details = project.project_status == 'awaiting_posm_details'
    had_no_customers_before = len(project.project_customers) == 0

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

        # ── B11: Snapshot old values before any mutation ─────────────────────
        def _fmt_date(d):
            return d.strftime('%d %b %Y') if d else '—'

        old_snapshot = {
            'name':                 project.name,
            'client':               project.client_brand.name if project.client_brand else '—',
            'cs_lead':              project.cs_lead.name if project.cs_lead else '—',
            'job_number':           project.job_number or '—',
            'urgency':              project.urgency or '—',
            'teams':                project.design_teams_requested or '—',
            'first_output_deadline': _fmt_date(project.first_output_deadline),
            'execution_date':       _fmt_date(project.execution_date),
            'concept_deadline':     _fmt_date(project.concept_deadline),
            'has_concept':          project.has_concept,
            'has_kv':               project.has_kv,
        }
        # ─────────────────────────────────────────────────────────────────────

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
                    return {'name': x.strip(), 'design_deadline': None, 'design_deadline_time': None, 'teams': []}
                return {
                    'name': (x.get('name') or '').strip(),
                    'design_deadline': x.get('design_deadline'),
                    'design_deadline_time': x.get('design_deadline_time'),
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
                    new_std_deliverable = Deliverable(
                        project_id=project.id,
                        project_customer_id=None,
                        deliverable_type_id=None,
                        name=item['name'],
                        design_deadline=del_deadline,
                        design_deadline_time=del_time,
                        teams=del_teams,
                        status='in_queue',
                        created_by=current_user
                    )
                    db.session.add(new_std_deliverable)
                    db.session.flush()  # need its id for the status log row
                    record_deliverable_status(new_std_deliverable, 'in_queue', actor)
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

                is_new_pc = False  # reset every iteration — only True when the else branch below runs

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
                    is_new_pc = True

                db.session.flush()
                if is_new_pc:
                    # Seed the status log for a brand-new customer row — need
                    # the flush above first so pc.id exists.
                    record_customer_status(pc, pc.status, actor)
                    is_new_pc = False
                customer_map[customer_id] = pc.id
            
            # --- Stage 3: rebuild deliverables for surviving customers ---
            # Must delete assignments first — bulk SQL DELETE bypasses ORM cascade,
            # so Postgres raises a FK violation if assignments still reference the deliverables.
            for pc_id in customer_map.values():
                deliverable_ids = [
                    row.id for row in
                    Deliverable.query.filter_by(project_customer_id=pc_id).with_entities(Deliverable.id)
                ]
                if deliverable_ids:
                    DeliverableAssignment.query.filter(
                        DeliverableAssignment.deliverable_id.in_(deliverable_ids)
                    ).delete(synchronize_session=False)
                Deliverable.query.filter_by(
                    project_customer_id=pc_id
                ).delete(synchronize_session=False)
            db.session.flush()

            for item in data.get('deliverables', []):
                customer_id = int(item['customer_id'])
                new_ccm_deliverable = Deliverable(
                    project_id=project.id,
                    project_customer_id=customer_map[customer_id],
                    deliverable_type_id=int(item['type_id']) if item.get('type_id') and item['type_id'] != 'custom' else None,
                    name=item['name'],
                    created_by=current_user
                )
                db.session.add(new_ccm_deliverable)
                db.session.flush()  # need its id for the status log row
                record_deliverable_status(new_ccm_deliverable, new_ccm_deliverable.status, actor)

        db.session.commit()

        # Sync NAS folder tree in background — creates any folders added by this edit.
        # Idempotent: force_parent=true means existing folders are silently skipped.
        _pid = project.id
        from flask import current_app as _app
        from app.nas import _run_in_background, create_project_folders
        from app.models import Project as _Project
        _app_obj = _app._get_current_object()
        _run_in_background(_app_obj, lambda: create_project_folders(_Project.query.get(_pid)))

        # -- POSM resume notification ---
        # Fires exactly once: when this project was paused (awaiting_posm_details)
        # with zero customers, and this edit is the one that gave it its first
        # customer(s). Reusing was_awaiting_posm_details/had_no_customers_before
        # from before the mutation, not the current state, is what keeps this
        # from re-firing on every subsequent edit to the same project.
        if (project.brief_type != 'standard' and was_awaiting_posm_details
                and had_no_customers_before and submitted_customer_ids):
            from app.notifications import notify_of_posm_details_added
            notify_of_posm_details_added(project, triggered_by=actor)

        # -- Field-level change logs ---
        new_client = project.client_brand.name if project.client_brand else '—'
        new_cs_lead = project.cs_lead.name if project.cs_lead else '—'

        field_changes = [
            (old_snapshot['name']                != project.name,                f'Name changed from "{old_snapshot["name"]}" to "{project.name}"'),
            (old_snapshot['client']              != new_client,                  f'Client changed from "{old_snapshot["client"]}" to "{new_client}"'),
            (old_snapshot['cs_lead']             != new_cs_lead,                 f'CS Lead changed from "{old_snapshot["cs_lead"]}" to "{new_cs_lead}"'),
            (old_snapshot['job_number']          != (project.job_number or '—'), f'Job number changed from "{old_snapshot["job_number"]}" to "{project.job_number or "—"}"'),
            (old_snapshot['urgency']             != (project.urgency or '—'),    f'Urgency changed from "{old_snapshot["urgency"]}" to "{project.urgency or "—"}"'),
            (old_snapshot['teams']               != (project.design_teams_requested or '—'), f'Design teams changed from "{old_snapshot["teams"]}" to "{project.design_teams_requested or "—"}"'),
            (old_snapshot['first_output_deadline'] != _fmt_date(project.first_output_deadline), f'First output deadline changed from {old_snapshot["first_output_deadline"]} to {_fmt_date(project.first_output_deadline)}'),
            (old_snapshot['execution_date']      != _fmt_date(project.execution_date),         f'Final deadline changed from {old_snapshot["execution_date"]} to {_fmt_date(project.execution_date)}'),
            (old_snapshot['concept_deadline']    != _fmt_date(project.concept_deadline),       f'Concept deadline changed from {old_snapshot["concept_deadline"]} to {_fmt_date(project.concept_deadline)}'),
            (old_snapshot['has_concept']         != project.has_concept,         f'Concept {"added" if project.has_concept else "removed"}'),
            (old_snapshot['has_kv']              != project.has_kv,              f'KV {"added" if project.has_kv else "removed"}'),
        ]

        for changed, msg in field_changes:
            if changed:
                log_activity('project_field_changed', msg,
                             user=actor,entity_type='project', entity_name=project.name, entity_id=project.id)
                
        log_activity('project_edited', f'Project "{project.name}" was edited by {actor.name}',
                     user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
        
        return jsonify({'success': True, 'redirect_url': url_for('project_detail.detail', project_id=project.id)})

    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Something went wrong. Please try again.'}), 500


@brief_bp.route('/projects/autosave', methods=['POST'])
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
            record_project_status(draft, 'draft', current_user)

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

@brief_bp.route('/projects/generate-job-number', methods=['GET'])
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
@brief_bp.route('/projects/<int:project_id>/download-brief')
@login_required
def download_brief(project_id):
    project = Project.query.get_or_404(project_id)
    return send_from_directory(
        current_app.config['UPLOAD_FOLDER'],
        project.brief_file,
        as_attachment=True
    )

@brief_bp.route('/<int:project_id>/delete', methods=['POST'])
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


@brief_bp.route('/projects/drafts')
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


@brief_bp.route('/projects/drafts/<int:draft_id>/delete', methods=['POST'])
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

@brief_bp.route('/projects/deliverable-types/<int:customer_id>')
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
        'is_custom': dt.is_custom,
        'reference_image': dt.reference_image
    } for dt in types])


@brief_bp.route('/clients/add', methods=['POST'])
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
    
@brief_bp.route('/projects/deliverable-types/add', methods=['POST'])
@login_required
@role_required('cs', 'admin', 'management')
def add_deliverable_type():
    try:
        data = request.get_json()

        name = data.get('name', '').strip()
        client_id = data.get('client_id')
        customer_id = data.get('customer_id')
        disciplines = data.get('disciplines', [])
        reference_image = data.get('reference_image')

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
            is_custom=True,
            reference_image=reference_image
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
            'is_custom': True,
            'reference_image': new_type.reference_image
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Something went wrong. Please try again.'}), 500
    
@brief_bp.route('/projects/deliverable-types/upload-image', methods=['POST'])
@login_required
@role_required('cs', 'admin', 'management')
def upload_deliverable_type_image():
    """Upload a reference image for a DeliverableType. Shared by both the
    Admin Panel's Deliverable Types form and the inline "+ Add custom
    deliverable" quick-add during C&CM briefing — same permission set as
    add_deliverable_type() above, since both flows create/edit the same
    resource. This route only saves the file and hands back its filename;
    it doesn't touch the DB itself, since it has no idea yet which
    DeliverableType (new or existing) the image belongs to — the caller
    folds the returned filename into its own create/update request."""
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
    

