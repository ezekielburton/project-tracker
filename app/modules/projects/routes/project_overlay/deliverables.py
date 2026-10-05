"""
project_overlay/deliverables.py — the Deliverables page: read view, Edit
Deliverables (Standard + C&CM save), Apply to Multiple (preview/confirm),
team assignment, and the Details people pickers (Project Owner, CS Lead,
Secondary CS, Concept/KV, Design Leads).

_DELIVERABLE_STATUS_OVERRIDE_OPTIONS lives in ._common because details.py
uses it too (as _PROJECT_STATUS_OVERRIDE_OPTIONS).
"""

from flask import render_template, abort, request, jsonify
from flask_login import login_required

from app.modules.core.shared.models import Project
from app.modules.projects.lib.teams import assignable_teams_for
from app.modules.core.shared.lib import org
from app.modules.core.shared.lib.capabilities import can

from ._common import (
    project_overlay_bp,
    _get_actor,
    _can_manage_deliverables,
    _has_edit_access_grant,
    _can_manage_flags,
    _can_resolve_flag,
    _build_ccm_deliverable_sections,
    _recompute_initial_deadline,
    _DELIVERABLE_STATUS_OVERRIDE_OPTIONS,
)

def _can_skip_preproduction(project, actor):
    """Skip to Pre-Production: admin/management, this project's CS Lead or
    Secondary CS, or the assigned Project Owner. A copy of the same helper
    lives in project_preproduction.py; keep the two in sync."""
    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    return (
        can('manage_projects', actor)
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
        or (can('claim_ownership', actor) and actor.id == project.project_owner_id)
    )


_TEAM_CANONICAL = {'2d': '2D', '3d': '3D', 'technical': 'Technical'}


def _canonical_team(raw):
    """Normalize a team string to User.team's casing ('2D'/'3D'/'Technical').
    Stored discipline and Deliverable.teams values may be lowercase, and
    assignment matches on exact User.team."""
    if not raw:
        return raw
    return _TEAM_CANONICAL.get(raw.strip().lower(), raw.strip())


def _needed_teams(d):
    """Teams a deliverable needs, in display order and canonical casing:
    its type's disciplines, else the free-text Deliverable.teams."""
    if d.deliverable_type and d.deliverable_type.disciplines:
        return [_canonical_team(disc.team) for disc in d.deliverable_type.disciplines]
    if d.teams:
        return [_canonical_team(t) for t in d.teams.split(',') if t]
    return []


def _build_deliverable_focus_context(deliverables, actor, can_manage_project, has_edit_access_grant=False):
    """Status pills, Focused/All data and team-tag assignment data
    (assign_by_deliverable) for both Deliverables views. The tag's write
    side is assign_deliverable_team.
    """
    from app.modules.core.shared.lib.status_vocabulary import derive_deliverable_status
    from app.modules.core.shared.services.status_tracking import bulk_deliverable_status_started_at
    from app.modules.core.shared.models import User
    from app.modules.core.shared.lib.users import active_users_query
    status_by_id = {}
    assigned_ids = set()
    for d in deliverables:
        status_by_id[d.id] = derive_deliverable_status(d)
        if any(a.designer_id == actor.id for a in d.disciplines):
            assigned_ids.add(d.id)
    status_started_at_by_id = bulk_deliverable_status_started_at([d.id for d in deliverables])

    # One options query per team in use (at most 3), not per row.
    needed_teams = set()
    for d in deliverables:
        needed_teams.update(_needed_teams(d))
    options_by_team = {
        team: active_users_query().filter(User.role.in_(['designer', 'team_lead']), User.team.in_(assignable_teams_for(team)))
                         .order_by(User.name).all()
        for team in needed_teams
    }

    assign_by_deliverable = {}
    for d in deliverables:
        assignment_by_team = {a.team: a for a in d.disciplines}
        row = []
        for team in _needed_teams(d):
            existing = assignment_by_team.get(team)
            # A lead manages their own team's tag; a designer can only
            # self-assign. Not can(): admin gets 'manage' through
            # can_manage_project, so the wildcard must not apply here.
            if can_manage_project or (org.is_design_lead(actor) and actor.team in assignable_teams_for(team)):
                mode = 'manage'
            elif org.is_plain_designer(actor) and actor.team in assignable_teams_for(team):
                mode = 'self'
            else:
                mode = 'static'
            row.append({
                'team': team,
                'person': existing.designer if existing else None,
                'mode': mode,
                'options': options_by_team.get(team, []),
            })
        assign_by_deliverable[d.id] = row

    return {
        'status_by_id': status_by_id,
        'status_started_at_by_id': status_started_at_by_id,
        'assigned_ids': assigned_ids,
        'assign_by_deliverable': assign_by_deliverable,
        # Designer/Team Lead/Admin get the toggle; everyone else always sees All.
        'can_toggle_focus': can('claim_work', actor),
        # Designers and leads start on Focused; admin starts on All. Not
        # can('claim_work'): admin holds it through the wildcard.
        'default_focus': org.is_designer(actor),
        # Admin, or a designer with an approved edit-access grant.
        'can_override_status': can('override_status', actor) or has_edit_access_grant,
        'deliverable_status_options': _DELIVERABLE_STATUS_OVERRIDE_OPTIONS,
    }


# Time dropdown slots, 8 AM–10 PM hourly, as (24h "HH:00" value, 12h label).
DESIGN_DEADLINE_TIME_OPTIONS = [
    (f'{h:02d}:00', f'{((h - 1) % 12) + 1}:00 {"AM" if h < 12 else "PM"}')
    for h in range(8, 23)
]

_DESIGN_DEADLINE_TIME_VALUES = {v for v, _ in DESIGN_DEADLINE_TIME_OPTIONS}


def _annotate_offhour_time(deliverables):
    """Set d.edit_time_extra = (value, label) for a stored time not in
    DESIGN_DEADLINE_TIME_OPTIONS, so the template adds it as an option.
    Without it the dropdown shows blank and the next Save wipes the time."""
    for d in deliverables:
        d.edit_time_extra = None
        t = d.design_deadline_time
        if t and t.strftime('%H:%M') not in _DESIGN_DEADLINE_TIME_VALUES:
            hour12 = ((t.hour - 1) % 12) + 1
            period = 'AM' if t.hour < 12 else 'PM'
            d.edit_time_extra = (t.strftime('%H:%M'), f'{hour12}:{t.minute:02d} {period}')


@project_overlay_bp.route('/projects/<int:project_id>/overlay/deliverables')
@login_required
def overlay_deliverables(project_id):
    from app.modules.core.shared.models import BriefFlag, Deliverable, DeliverableType, DeliverableAssignment
    from sqlalchemy.orm import selectinload, joinedload
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    can_manage = _can_manage_deliverables(project, actor)
    can_manage_flags = _can_manage_flags(actor)
    can_skip_preproduction = _can_skip_preproduction(project, actor)
    # Lets a granted designer see the status override.
    has_edit_access_grant = _has_edit_access_grant(project, actor)

    # Open deliverable flags, one query, grouped by deliverable_id. A plain
    # dict (not defaultdict) so the template's `d.id in ...` check stays honest.
    open_flags = (
        BriefFlag.query
        .filter_by(project_id=project_id, flag_type='deliverable', is_resolved=False)
        .order_by(BriefFlag.created_at)
        .all()
    )
    open_flags_by_deliverable_id = {}
    for f in open_flags:
        f.can_resolve = _can_resolve_flag(f, actor)
        open_flags_by_deliverable_id.setdefault(f.deliverable_id, []).append(f)

    if project.brief_type == 'ccm':
        regions = _build_ccm_deliverable_sections(project)
        has_gulf_regions = any(r['key'] in ('kuwait', 'qatar', 'bahrain', 'oman') for r in regions)
        all_customers = [c for r in regions for c in r['customers']]
        first_customer_id = all_customers[0]['project_customer'].id if all_customers else None
        all_deliverables = [d for c in all_customers for d in c['deliverables']]
        # Needs Attention is per customer: only flags on its own deliverables.
        for c in all_customers:
            c['open_flags'] = [f for d in c['deliverables'] for f in open_flags_by_deliverable_id.get(d.id, [])]
        return render_template(
            'project_overlay/_deliverables_ccm.html',
            project=project,
            regions=regions,
            all_customers=all_customers,
            all_deliverables=all_deliverables, # flat list — feeds the Skip to Pre-Production picker
            has_gulf_regions=has_gulf_regions,
            first_customer_id=first_customer_id,
            can_manage_deliverables=can_manage,
            can_skip_preproduction=can_skip_preproduction,
            can_manage_flags=can_manage_flags,
            open_flags_by_deliverable_id=open_flags_by_deliverable_id,
            **_build_deliverable_focus_context(all_deliverables, actor, can_manage, has_edit_access_grant),
        )

    # Eager-load what the team tags read, to avoid a query per row.
    deliverables = (
        Deliverable.query.filter_by(project_id=project_id, project_customer_id=None)
        .options(
            selectinload(Deliverable.disciplines).joinedload(DeliverableAssignment.designer),
            selectinload(Deliverable.deliverable_type).selectinload(DeliverableType.disciplines),
        )
        .order_by(Deliverable.id)
        .all()
    )
    return render_template(
        'project_overlay/_deliverables_standard.html',
        project=project,
        deliverables=deliverables,
        can_manage_deliverables=can_manage,
        can_skip_preproduction=can_skip_preproduction,
        can_manage_flags=can_manage_flags,
        open_flags=open_flags,
        open_flags_by_deliverable_id=open_flags_by_deliverable_id,
        **_build_deliverable_focus_context(deliverables, actor, can_manage, has_edit_access_grant),
    )


@project_overlay_bp.route('/projects/<int:project_id>/overlay/deliverables/edit')
@login_required
def overlay_deliverables_edit(project_id):
    from app.modules.core.shared.models import Deliverable
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not _can_manage_deliverables(project, actor):
        abort(403)

    if project.brief_type == 'ccm':
        # Same builder as view mode, so the customer order matches between the two.
        regions = _build_ccm_deliverable_sections(project, with_catalog=True)
        has_gulf_regions = any(r['key'] in ('kuwait', 'qatar', 'bahrain', 'oman') for r in regions)
        all_customers = [c for r in regions for c in r['customers']]
        first_customer_id = all_customers[0]['project_customer'].id if all_customers else None
        _annotate_offhour_time([d for c in all_customers for d in c['deliverables']])
        return render_template(
            'project_overlay/_deliverables_ccm_edit.html',
            project=project,
            regions=regions,
            all_customers=all_customers,
            has_gulf_regions=has_gulf_regions,
            first_customer_id=first_customer_id,
            time_options=DESIGN_DEADLINE_TIME_OPTIONS,
        )

    deliverables = Deliverable.query.filter_by(
        project_id=project_id, project_customer_id=None
    ).order_by(Deliverable.id).all()
    _annotate_offhour_time(deliverables)
    return render_template(
        'project_overlay/_deliverables_standard_edit.html',
        project=project,
        deliverables=deliverables,
        time_options=DESIGN_DEADLINE_TIME_OPTIONS,
    )


@project_overlay_bp.route('/projects/<int:project_id>/overlay/deliverables/save', methods=['POST'])
@login_required
def save_standard_deliverables(project_id):
    """Bulk create/update/delete for Edit Deliverables, committed once. Both
    brief types: C&CM rows carry a project_customer_id, Standard rows don't.

    A C&CM row has a catalog pick (deliverable_type_id) or a new catalog
    name (new_type_name); with neither, the free-text `name` is used."""
    from datetime import datetime as dt
    from app.modules.core.shared.models import Deliverable, DeliverableType
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity
    from flask import request, jsonify, session

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not _can_manage_deliverables(project, actor):
        abort(403)

    data = request.get_json(silent=True) or {}
    rows = data.get('deliverables') or []

    # Rows send project_customers.id; the catalog keys on customers.id. Map
    # between them. An id not on this project parses to None.
    customer_by_pc = {pc.id: pc.customer_id for pc in project.project_customers}
    valid_customer_ids = set(customer_by_pc)

    def parse_date(val):
        if not val:
            return None
        try:
            return dt.strptime(val, '%Y-%m-%d').date()
        except ValueError:
            return None

    def parse_time(val):
        if not val:
            return None
        try:
            return dt.strptime(val, '%H:%M').time()
        except ValueError:
            return None

    def parse_customer_id(val):
        try:
            val = int(val)
        except (TypeError, ValueError):
            return None
        return val if val in valid_customer_ids else None

    # One fetch of every referenced customer's catalog, keyed by customers.id.
    # Also a security check: a type id only counts if it is in that customer's catalog.
    row_pc_ids = {parse_customer_id(r.get('project_customer_id')) for r in rows}
    row_pc_ids.discard(None)
    row_customer_ids = {customer_by_pc[pc_id] for pc_id in row_pc_ids}
    types_by_customer = {}
    if row_customer_ids:
        for t in DeliverableType.query.filter(DeliverableType.customer_id.in_(row_customer_ids)).all():
            types_by_customer.setdefault(t.customer_id, []).append(t)

    def lookup_type_by_id(customer_id, type_id):
        for t in types_by_customer.get(customer_id, []):
            if t.id == type_id:
                return t
        return None

    def lookup_type_by_name(customer_id, name):
        key = name.strip().lower()
        for t in types_by_customer.get(customer_id, []):
            if t.name.strip().lower() == key:
                return t
        return None

    created, updated, deleted = [], [], []

    for row in rows:
        row_id = row.get('id')

        if row_id and row.get('deleted'):
            deliverable = Deliverable.query.filter_by(id=row_id, project_id=project_id).first()
            if deliverable:
                deleted.append(deliverable.name)
                db.session.delete(deliverable)
            continue

        customer_id_for_row = parse_customer_id(row.get('project_customer_id'))
        real_customer_id = customer_by_pc.get(customer_id_for_row)
        design_deadline = parse_date(row.get('design_deadline'))
        design_deadline_time = parse_time(row.get('design_deadline_time'))
        teams = ','.join(row.get('teams') or [])

        resolved_type = None
        new_type_name = (row.get('new_type_name') or '').strip()
        raw_type_id = row.get('deliverable_type_id')

        if new_type_name and customer_id_for_row:
            # Reuse a same-named catalog entry if one exists.
            resolved_type = lookup_type_by_name(real_customer_id, new_type_name)
            if not resolved_type:
                resolved_type = DeliverableType(
                    name=new_type_name,
                    client_id=project.client_id,
                    customer_id=real_customer_id,
                    is_custom=True,
                )
                db.session.add(resolved_type)
                # So a later row with the same new name reuses this one.
                types_by_customer.setdefault(real_customer_id, []).append(resolved_type)
            name = resolved_type.name
        elif raw_type_id and customer_id_for_row:
            try:
                resolved_type = lookup_type_by_id(real_customer_id, int(raw_type_id))
            except (TypeError, ValueError):
                resolved_type = None
            name = resolved_type.name if resolved_type else (row.get('name') or '').strip()
        else:
            # Standard, or a C&CM row with no catalog link: free-text name.
            name = (row.get('name') or '').strip()

        if not name:
            continue # skip blank rows rather than fail the whole save

        if row_id:
            deliverable = Deliverable.query.filter_by(id=row_id, project_id=project_id).first()
            if not deliverable:
                continue
            deliverable.name = name
            deliverable.design_deadline = design_deadline
            deliverable.design_deadline_time = design_deadline_time
            deliverable.teams = teams
            if resolved_type is not None:
                deliverable.deliverable_type = resolved_type
            updated.append(deliverable.name)
        else:
            deliverable = Deliverable(
                project_id=project_id,
                project_customer_id=customer_id_for_row,
                deliverable_type=resolved_type,
                name=name,
                design_deadline=design_deadline,
                design_deadline_time=design_deadline_time,
                teams=teams,
                status='in_queue',
                created_by=actor,
            )
            db.session.add(deliverable)
            created.append(name)

    # Initial Deadline follows deliverable dates for drafts only. On a live
    # project it may have been set by hand, so leave it alone.
    if project.project_status == 'draft':
        _recompute_initial_deadline(project)
    db.session.commit()

    for name in created:
        log_activity('deliverable_created', f'Deliverable "{name}" added to "{project.name}"',
                     user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    for name in updated:
        log_activity('deliverable_updated', f'Deliverable "{name}" updated on "{project.name}"',
                     user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    for name in deleted:
        log_activity('deliverable_deleted', f'Deliverable "{name}" removed from "{project.name}"',
                     user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})


def _apply_multiple_compute(project, source_customer_id, target_customer_ids):
    """Read-only match for Apply to Multiple, used by preview and confirm.
    Returns (source_deliverables, per_target); per_target is keyed by target
    ProjectCustomer.id with 'will_add', 'already_existing' and 'missing'
    lists. (None, None) if any id isn't on this project."""
    from app.modules.core.shared.models import Deliverable, DeliverableType, ProjectCustomer

    try:
        source_id_int = int(source_customer_id)
        target_ids_int = [int(x) for x in target_customer_ids]
    except (TypeError, ValueError):
        return None, None

    source_pc = ProjectCustomer.query.filter_by(id=source_id_int, project_id=project.id).first()
    target_pcs = ProjectCustomer.query.filter(
        ProjectCustomer.id.in_(target_ids_int), ProjectCustomer.project_id == project.id
    ).all()
    if not source_pc or not target_pcs or len(target_pcs) != len(set(target_ids_int)):
        return None, None

    source_deliverables = Deliverable.query.filter_by(
        project_id=project.id, project_customer_id=source_pc.id
    ).order_by(Deliverable.id).all()

    target_pc_ids = [pc.id for pc in target_pcs]
    target_customer_ids_real = {pc.id: pc.customer_id for pc in target_pcs}

    existing_by_target = {}
    for d in Deliverable.query.filter(
        Deliverable.project_id == project.id,
        Deliverable.project_customer_id.in_(target_pc_ids),
    ).all():
        existing_by_target.setdefault(d.project_customer_id, set()).add(d.name.strip().lower())

    catalog_by_customer = {}
    for t in DeliverableType.query.filter(
        DeliverableType.customer_id.in_(set(target_customer_ids_real.values())),
        DeliverableType.is_active.is_(True),
    ).all():
        catalog_by_customer.setdefault(t.customer_id, {})[t.name.strip().lower()] = t

    per_target = {}
    for pc in target_pcs:
        already = existing_by_target.get(pc.id, set())
        catalog = catalog_by_customer.get(pc.customer_id, {})
        will_add, already_existing, missing = [], [], []
        for d in source_deliverables:
            key = d.name.strip().lower()
            if key in already:
                already_existing.append(d)
            elif key in catalog:
                will_add.append((d, catalog[key]))
            else:
                missing.append(d)
        per_target[pc.id] = {
            'project_customer': pc,
            'will_add': will_add,
            'already_existing': already_existing,
            'missing': missing,
        }
    return source_deliverables, per_target


@project_overlay_bp.route('/projects/<int:project_id>/overlay/deliverables/apply-multiple/preview', methods=['POST'])
@login_required
def preview_apply_deliverables_multiple(project_id):
    """Apply to Multiple preview: matched count and each target's missing
    list, no writes. Reads saved rows only; project_deliverables_card.js
    blocks the modal while there are unsaved edits."""
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not _can_manage_deliverables(project, actor):
        abort(403)

    data = request.get_json(silent=True) or {}
    source_customer_id = data.get('source_customer_id')
    target_customer_ids = data.get('target_customer_ids') or []

    source_deliverables, per_target = _apply_multiple_compute(project, source_customer_id, target_customer_ids)
    if source_deliverables is None:
        return jsonify({'success': False, 'error': 'Invalid customer selection.'}), 400
    if not source_deliverables:
        return jsonify({'success': False, 'error': 'This customer has no deliverables to duplicate.'}), 400

    targets_out = []
    total_will_add = 0
    for pc_id, info in per_target.items():
        total_will_add += len(info['will_add'])
        targets_out.append({
            'customer_id': pc_id,
            'customer_name': info['project_customer'].customer.name,
            'will_add_count': len(info['will_add']),
            'already_existing': [d.name for d in info['already_existing']],
            'missing': [{'id': d.id, 'name': d.name} for d in info['missing']],
        })

    return jsonify({'success': True, 'targets': targets_out, 'total_will_add': total_will_add})


@project_overlay_bp.route('/projects/<int:project_id>/overlay/deliverables/apply-multiple/confirm', methods=['POST'])
@login_required
def confirm_apply_deliverables_multiple(project_id):
    """Apply to Multiple write step. Re-runs _apply_multiple_compute so a
    change since the preview can't cause stale writes. All new rows are
    added in bulk and committed once."""
    from datetime import datetime as dt
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import DeliverableType, DeliverableTypeDiscipline, Deliverable
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not _can_manage_deliverables(project, actor):
        abort(403)

    data = request.get_json(silent=True) or {}
    source_customer_id = data.get('source_customer_id')
    target_customer_ids = data.get('target_customer_ids') or []
    # {str(target_customer_id): {'date': 'YYYY-MM-DD', 'time': 'HH:MM', 'create_missing_ids': [...]}}
    per_target_input = data.get('targets') or {}

    source_deliverables, per_target = _apply_multiple_compute(project, source_customer_id, target_customer_ids)
    if source_deliverables is None or not source_deliverables:
        return jsonify({'success': False, 'error': 'Invalid customer selection.'}), 400

    def parse_date(val):
        if not val:
            return None
        try:
            return dt.strptime(val, '%Y-%m-%d').date()
        except ValueError:
            return None

    def parse_time(val):
        if not val:
            return None
        try:
            return dt.strptime(val, '%H:%M').time()
        except ValueError:
            return None

    new_types, new_disciplines, new_deliverables = [], [], []
    duplicated_count = 0
    customers_touched = set()

    for pc_id, info in per_target.items():
        target_input = per_target_input.get(str(pc_id)) or {}
        deadline = parse_date(target_input.get('date'))
        deadline_time = parse_time(target_input.get('time'))
        try:
            create_missing_ids = {int(x) for x in (target_input.get('create_missing_ids') or [])}
        except (TypeError, ValueError):
            create_missing_ids = set()

        # Matched: the target's catalog already has this name.
        for source_d, matched_type in info['will_add']:
            new_deliverables.append(Deliverable(
                project_id=project.id,
                project_customer_id=pc_id,
                deliverable_type=matched_type,
                name=matched_type.name,
                design_deadline=deadline,
                design_deadline_time=deadline_time,
                teams=source_d.teams,
                status='in_queue',
                created_by=actor,
            ))
            duplicated_count += 1
            customers_touched.add(pc_id)

        # Missing but ticked: create a catalog entry, cloning teams/image/
        # template from the source's type (or just name/teams if it has none).
        for source_d in info['missing']:
            if source_d.id not in create_missing_ids:
                continue
            source_type = source_d.deliverable_type
            new_type = DeliverableType(
                name=source_d.name,
                client_id=project.client_id,
                customer_id=info['project_customer'].customer_id,
                reference_image=source_type.reference_image if source_type else None,
                template_filename=source_type.template_filename if source_type else None,
                is_custom=True,
            )
            new_types.append(new_type)
            if source_type and source_type.disciplines:
                for disc in source_type.disciplines:
                    new_disciplines.append(DeliverableTypeDiscipline(deliverable_type=new_type, team=disc.team))
            elif source_d.teams:
                for team in source_d.teams.split(','):
                    if team:
                        new_disciplines.append(DeliverableTypeDiscipline(deliverable_type=new_type, team=team))

            new_deliverables.append(Deliverable(
                project_id=project.id,
                project_customer_id=pc_id,
                deliverable_type=new_type,
                name=source_d.name,
                design_deadline=deadline,
                design_deadline_time=deadline_time,
                teams=source_d.teams,
                status='in_queue',
                created_by=actor,
            ))
            duplicated_count += 1
            customers_touched.add(pc_id)

    if not new_deliverables:
        return jsonify({
            'success': False,
            'error': 'Nothing to apply. Every matching deliverable is already on the selected customers.',
        }), 400

    # New rows link to new_types by relationship, not id; SQLAlchemy fills
    # the FKs at flush.
    db.session.add_all(new_types)
    db.session.add_all(new_disciplines)
    db.session.add_all(new_deliverables)
    db.session.commit()

    message = 'Duplicated {} deliverable{} across {} customer{}.'.format(
        duplicated_count, '' if duplicated_count == 1 else 's',
        len(customers_touched), '' if len(customers_touched) == 1 else 's',
    )
    log_activity('deliverables_duplicated', f'{message} ("{project.name}")',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({
        'success': True,
        'duplicated_count': duplicated_count,
        'customer_count': len(customers_touched),
        'message': message,
    })


def _can_write_deliverable_assignment(project, actor, team, target_designer_id, existing_assignment):
    """Who may set or clear any assignment on one deliverable's team: anyone
    passing _can_manage_deliverables, or that team's own team lead. Plain
    designers use the self_toggle path instead."""
    if _can_manage_deliverables(project, actor):
        return True
    # Team rule, not a capability: depends on actor.team as well as seniority.
    if org.is_design_lead(actor) and actor.team in assignable_teams_for(team):
        return True
    return False


@project_overlay_bp.route('/projects/<int:project_id>/overlay/deliverables/assign', methods=['POST'])
@login_required
def assign_deliverable_team(project_id):
    """Set a deliverable's team assignment from the Team column tags.

    - self_toggle: a designer claims/releases their own slot. Never
      overwrites a teammate (409 if someone else holds it).
    - designer_id (None clears): _can_write_deliverable_assignment holders
      set anyone on the team.

    The same DeliverableAssignment row carries into Pre-Production, where
    project_preproduction's assign_stream() can change it."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import Deliverable, DeliverableAssignment, User
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    data = request.get_json(silent=True) or {}
    deliverable_id = data.get('deliverable_id')
    # Normalize so a lowercase team from a stale page or API call can't
    # create a second, differently-cased assignment row.
    team = _canonical_team(data.get('team'))
    deliverable = Deliverable.query.get(deliverable_id) if deliverable_id else None
    if not deliverable or deliverable.project_id != project_id or not team:
        return jsonify({'success': False, 'error': 'Could not find that deliverable.'}), 400

    existing = DeliverableAssignment.query.filter_by(
        deliverable_id=deliverable.id, team=team
    ).first()

    if data.get('self_toggle'):
        if not org.is_plain_designer(actor) or actor.team not in assignable_teams_for(team):
            return jsonify({'success': False, 'error': 'You do not have permission to assign this.'}), 403
        if existing and existing.designer_id == actor.id:
            db.session.delete(existing)
            db.session.commit()
            log_activity('deliverable_unassigned',
                         f'{actor.name} removed themself from {team} on "{deliverable.name}" ({project.name})',
                         user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
            return jsonify({'success': True, 'designer_id': None})
        if existing:
            # Someone else claimed it since the page rendered; never steal it.
            return jsonify({
                'success': False,
                'error': f'{existing.designer.name} is already assigned to {team} on this deliverable.',
            }), 409
        db.session.add(DeliverableAssignment(
            deliverable_id=deliverable.id, team=team,
            designer_id=actor.id, assigned_by_id=actor.id,
        ))
        db.session.commit()
        log_activity('deliverable_assigned',
                     f'{actor.name} assigned themself to {team} on "{deliverable.name}" ({project.name})',
                     user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
        return jsonify({'success': True, 'designer_id': actor.id})

    if not _can_write_deliverable_assignment(project, actor, team, None, existing):
        return jsonify({'success': False, 'error': 'You do not have permission to assign this.'}), 403

    raw_designer_id = data.get('designer_id')
    designer_id = int(raw_designer_id) if raw_designer_id else None

    if designer_id is None:
        if existing:
            db.session.delete(existing)
            db.session.commit()
            log_activity('deliverable_unassigned',
                         f'{actor.name} removed the {team} assignment from "{deliverable.name}" ({project.name})',
                         user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
        return jsonify({'success': True, 'designer_id': None})

    target = User.query.get(designer_id)
    # About the person being assigned, not the caller — validation, not a gate.
    if not target or not org.is_designer(target) or target.team not in assignable_teams_for(team):
        return jsonify({'success': False, 'error': f'That person cannot be assigned to the {team} team.'}), 400

    if existing:
        existing.designer_id = designer_id
        existing.assigned_by_id = actor.id
    else:
        db.session.add(DeliverableAssignment(
            deliverable_id=deliverable.id, team=team,
            designer_id=designer_id, assigned_by_id=actor.id,
        ))
    db.session.commit()
    log_activity('deliverable_assigned',
                 f'{actor.name} assigned {target.name} to {team} on "{deliverable.name}" ({project.name})',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    return jsonify({'success': True, 'designer_id': designer_id})


@project_overlay_bp.route('/projects/<int:project_id>/set-project-owner', methods=['POST'])
@login_required
def set_project_owner(project_id):
    """Assign or reassign the Project Owner. Allowed for admin/management,
    this project's CS Lead, or a Project Owner claiming it for themselves."""
    from app.modules.core.shared.models import Project, User
    from flask import request, jsonify
    from app.modules.projects.services import mutations as project_mutations

    project = Project.query.get_or_404(project_id)

    actor = _get_actor()

    new_owner_id = request.form.get('user_id', type=int)
    if not new_owner_id:
        return jsonify({'success': False, 'error': 'Please select a Project Owner.'}), 400

    is_self_claim = (can('claim_ownership', actor) and new_owner_id == actor.id)

    if not can('manage_projects', actor) and actor.id != project.cs_lead_id and not is_self_claim:
        return jsonify({'success': False, 'error': 'You are lacking permissions to perform this action.'}), 403

    new_owner = User.query.get(new_owner_id)
    # About the person being assigned, not the caller.
    if not new_owner or not org.is_project_owner(new_owner):
        return jsonify({'success': False, 'error': 'Selected user is not a Project Owner'}), 400

    # Shared with the Client Servicing table (write, notify, log).
    project_mutations.set_project_owner(project, new_owner, actor)
    return jsonify({'success': True, 'owner_name': new_owner.name})


# ── Details page people-picker routes ──
# project_details_card.js POSTs to these and parses every response as JSON,
# so return JSON errors, never abort().
@project_overlay_bp.route('/projects/<int:project_id>/reassign-cs-lead', methods=['POST'])
@login_required
def reassign_cs_lead(project_id):
    """CS Lead picker on the Details page. Admin/management only."""
    from app.modules.core.shared.models import User
    from app.modules.projects.services import mutations as project_mutations

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    if not can('manage_projects', actor):
        return jsonify({'success': False, 'error': 'Only admin/management can reassign a CS lead.'}), 403

    new_cs_lead_id = (request.get_json(silent=True) or {}).get('new_cs_lead_id')
    if not new_cs_lead_id:
        return jsonify({'success': False, 'error': 'A new CS lead is required.'}), 400

    new_cs_lead = User.query.get(int(new_cs_lead_id))
    # About the person being assigned, not the caller.
    if not new_cs_lead or not org.is_cs(new_cs_lead):
        return jsonify({'success': False, 'error': 'CS lead not found.'}), 404

    project_mutations.reassign_cs_lead(project, new_cs_lead, actor)
    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/secondary-cs', methods=['POST'])
@login_required
def add_secondary_cs(project_id):
    """Add a secondary CS. Gate must match _build_details_context's
    can_manage_cs (admin/management, or this project's CS Lead), which
    decides whether the picker renders."""
    from app.modules.core.shared.models import User, ProjectSecondaryCS
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    if not can('manage_projects', actor) and actor.id != project.cs_lead_id:
        return jsonify({'success': False, 'error': 'You do not have permission to add a secondary CS.'}), 403

    user_id = request.form.get('user_id', type=int)
    if not user_id:
        return jsonify({'success': False, 'error': 'Please select a CS member.'}), 400

    if user_id == project.cs_lead_id:
        return jsonify({'success': False, 'error': 'The CS lead is already the primary CS on this project.'}), 400

    user = User.query.get(user_id)
    # About the person being added, not the caller.
    if not user or not (org.is_cs(user) or org.is_leadership(user)):
        return jsonify({'success': False, 'error': 'Only CS & Management members can be added as secondary CS.'}), 400

    if ProjectSecondaryCS.query.filter_by(project_id=project_id, user_id=user_id).first():
        return jsonify({'success': False, 'error': 'Already a secondary CS on this project.'}), 400

    db.session.add(ProjectSecondaryCS(project_id=project_id, user_id=user_id, added_by_id=actor.id))
    db.session.commit()

    log_activity('secondary_cs_added', f'{user.name} added as secondary CS on "{project.name}"',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/secondary-cs/<int:user_id>/remove', methods=['POST'])
@login_required
def remove_secondary_cs(project_id, user_id):
    """Remove a secondary CS — same permission as add_secondary_cs. Also clears
    their ProjectSecondaryCsRegion rows to avoid orphaned subscriptions."""
    from app.modules.core.shared.models import User, ProjectSecondaryCS, ProjectSecondaryCsRegion
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    if not can('manage_projects', actor) and actor.id != project.cs_lead_id:
        return jsonify({'success': False, 'error': 'You do not have permission to remove a secondary CS.'}), 403

    assignment = ProjectSecondaryCS.query.filter_by(project_id=project_id, user_id=user_id).first()
    if not assignment:
        return jsonify({'success': False, 'error': 'Not a secondary CS on this project.'}), 404

    user = User.query.get(user_id)
    ProjectSecondaryCsRegion.query.filter_by(project_id=project_id, user_id=user_id).delete()
    db.session.delete(assignment)
    db.session.commit()

    log_activity('secondary_cs_removed',
                 f'{user.name if user else "User"} removed as secondary CS on "{project.name}"',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/assign-concept-kv', methods=['POST'])
@login_required
def assign_concept_kv(project_id):
    """Concept & KV Designer picker on the Details page. Admin/management
    assign anyone; designer/team_lead can only self-claim. Matches the
    picker gates in _build_details_context."""
    from app.modules.core.shared.models import User
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.services.notifications import notify_designer_of_concept_kv_assignment

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    full_control = can('manage_projects', actor)
    # Not can('claim_work'): admin would land in the self-claim branch.
    self_claim_only = org.is_designer(actor)
    if not full_control and not self_claim_only:
        return jsonify({'success': False, 'error': 'You do not have permission to assign this.'}), 403

    concept_id = request.form.get('concept_designer_id')
    kv_id = request.form.get('kv_designer_id')

    if self_claim_only:
        if concept_id and int(concept_id) != actor.id:
            return jsonify({'success': False, 'error': 'You can only assign yourself.'}), 403
        if kv_id and int(kv_id) != actor.id:
            return jsonify({'success': False, 'error': 'You can only assign yourself.'}), 403

    if concept_id:
        project.concept_designer_id = int(concept_id)
    if kv_id:
        project.kv_designer_id = int(kv_id)
    db.session.commit()

    if concept_id:
        concept_designer = User.query.get(int(concept_id))
        if concept_designer:
            notify_designer_of_concept_kv_assignment(project, concept_designer, 'Concept', triggered_by=actor)
            log_activity('designer_assigned', f'{concept_designer.name} assigned as Concept designer on "{project.name}"',
                         user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    if kv_id:
        kv_designer = User.query.get(int(kv_id))
        if kv_designer:
            notify_designer_of_concept_kv_assignment(project, kv_designer, 'Key Visual', triggered_by=actor)
            log_activity('designer_assigned', f'{kv_designer.name} assigned as KV designer on "{project.name}"',
                         user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/assign-lead', methods=['POST'])
@login_required
def assign_lead(project_id):
    """Design Leads per-team picker on the Details page. Picking yourself is
    allowed for your own team (fill or take over); picking someone else is a
    transfer, allowed only for the current lead or admin/management.

    ProjectDesigner is UNIQUE(project_id, team): delete and flush the old row
    before inserting, or the INSERT fails."""
    from app.modules.core.shared.models import User, ProjectDesigner
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.services.notifications import notify_cs_of_lead_change

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    data = request.get_json(silent=True) or {}
    team = (data.get('team') or '').strip()
    raw_target_id = data.get('new_designer_id')

    if not team:
        return jsonify({'success': False, 'error': 'Team is required.'}), 400

    # Designers stay in their own team; admin is exempt.
    if org.is_designer(actor) and actor.team not in assignable_teams_for(team):
        return jsonify({'success': False, 'error': 'You can only assign yourself to your own team.'}), 403

    target_id = int(raw_target_id) if raw_target_id else actor.id
    is_self = (target_id == actor.id)

    current_assignment = ProjectDesigner.query.filter_by(project_id=project.id, team=team).first()
    previous_designer = current_assignment.designer if current_assignment else None

    if not is_self:
        # Transfer to someone else: current lead or admin/management only.
        if not can('manage_projects', actor):
            if not current_assignment or current_assignment.user_id != actor.id:
                return jsonify({'success': False, 'error': 'Only the current lead can transfer ownership.'}), 403
        new_designer = User.query.get(target_id)
        if not new_designer:
            return jsonify({'success': False, 'error': 'Designer not found.'}), 404
        if current_assignment:
            db.session.delete(current_assignment)
            db.session.flush()
        db.session.add(ProjectDesigner(project_id=project.id, user_id=new_designer.id, team=team))
        db.session.commit()
        notify_cs_of_lead_change(project, new_designer, team, triggered_by=actor, previous_designer=previous_designer)
        log_activity('lead_transferred',
                     f'{actor.name} transferred {team} lead to {new_designer.name} on "{project.name}"',
                     user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
    else:
        # Self-claim or takeover, even if someone else holds the slot.
        if current_assignment:
            db.session.delete(current_assignment)
            db.session.flush()
        db.session.add(ProjectDesigner(project_id=project.id, user_id=actor.id, team=team))
        db.session.commit()
        notify_cs_of_lead_change(project, actor, team, triggered_by=actor, previous_designer=previous_designer)
        action = 'lead_transferred' if previous_designer else 'lead_assigned'
        description = (
            f'{actor.name} took over as {team} lead on "{project.name}" (previously {previous_designer.name})'
            if previous_designer
            else f'{actor.name} self-assigned as {team} lead on "{project.name}"'
        )
        log_activity(action, description, user=actor,
                     entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True})
