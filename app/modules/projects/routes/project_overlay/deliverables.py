"""
project_overlay/deliverables.py — the Deliverables sub-tab: read view,
Edit Deliverables (Standard + C&CM save), the multi-apply preview/confirm
flow, team assignment, and the project-people-picker actions (Project Owner,
CS Lead reassignment, Secondary CS, Concept/KV assignment, Lead assignment).

_DELIVERABLE_STATUS_OVERRIDE_OPTIONS lives in ._common because details.py's
_build_details_context needs it too.
"""

from flask import render_template, abort, request, jsonify
from flask_login import login_required, current_user

from app.modules.core.shared.models import Project
from app.modules.core.shared.lib.decorators import role_required

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
    """Who can use Skip to Pre-Production — CS Lead, Secondary CS,
    Management, Admin, or the assigned Project Owner (not any cs-role user —
    only someone with a relationship to this specific project). Same
    shape as _can_cancel_project. Kept as its own function rather than
    widening _can_manage_preproduction over in project_preproduction.py —
    Mark Done/Approve/Flag keep their existing, narrower gate. Duplicated
    there too (not cross-imported) matching this codebase's existing
    one-helper-per-route-file convention."""
    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    return (
        actor.role in ('admin', 'management')
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
        or (actor.role == 'project_owner' and actor.id == project.project_owner_id)
    )


_TEAM_CANONICAL = {'2d': '2D', '3d': '3D', 'technical': 'Technical'}


def _canonical_team(raw):
    """Normalizes a team string to the exact casing User.team/registration
    use ('2D'/'3D'/'Technical'). Needed because DeliverableTypeDiscipline.team
    (set via the admin Deliverable Types editor) and the free-text
    Deliverable.teams field aren't guaranteed to be saved in that casing —
    the edit form in admin.js stored them lowercase ('2d'/'3d'/'technical')
    historically, so plenty of existing rows still are. Nothing before
    the team-tag assignment feature (this file) cared about exact casing —
    display always went through .lower() anyway for the CSS class name —
    so this mismatch was invisible until an exact `User.team == team`
    match was needed. Normalizing here, at read time, means every
    deliverable's Assignments column works immediately regardless of
    which casing its own disciplines happen to be stored in, without
    needing a data migration or every type to be re-saved first."""
    if not raw:
        return raw
    return _TEAM_CANONICAL.get(raw.strip().lower(), raw.strip())


def _needed_teams(d):
    """Which teams (2D/3D/Technical) a deliverable actually needs, in
    display order — same source-of-truth branching the Team column
    template used to do inline (deliverable_type's own disciplines list,
    falling back to the free-text Deliverable.teams field for
    C&CM/manually-added rows with no catalogue type). Centralized here so
    _build_deliverable_focus_context can build the assignment context off
    the exact same list the template renders. Always returns canonically-
    cased team strings — see _canonical_team()."""
    if d.deliverable_type and d.deliverable_type.disciplines:
        return [_canonical_team(disc.team) for disc in d.deliverable_type.disciplines]
    if d.teams:
        return [_canonical_team(t) for t in d.teams.split(',') if t]
    return []


def _build_deliverable_focus_context(deliverables, actor, can_manage_project, has_edit_access_grant=False):
    """Per-deliverable status pill + Focused/All eligibility data shared by the
    Standard and C&CM Deliverables views.

    Also builds `assign_by_deliverable` — per deliverable and needed team, who's
    assigned and what clicking that team's tag does for the actor (the read side
    of the Team column's click-to-assign; the write side is
    assign_deliverable_team). has_edit_access_grant is passed in by callers,
    which already have the project/actor pair.
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
    # One bulk query for the whole roster rather than one per deliverable,
    # same pattern _bulk_deliverable_aggregates uses in project_list.
    status_started_at_by_id = bulk_deliverable_status_started_at([d.id for d in deliverables])

    # Options are per-team, not per-deliverable/per-row — one small query
    # per distinct team actually in use on this roster (at most 3:
    # 2D/3D/Technical), regardless of how many deliverables are showing.
    needed_teams = set()
    for d in deliverables:
        needed_teams.update(_needed_teams(d))
    options_by_team = {
        team: active_users_query().filter(User.role.in_(['designer', 'team_lead']), User.team == team)
                         .order_by(User.name).all()
        for team in needed_teams
    }

    assign_by_deliverable = {}
    for d in deliverables:
        assignment_by_team = {a.team: a for a in d.disciplines}
        row = []
        for team in _needed_teams(d):
            existing = assignment_by_team.get(team)
            if can_manage_project or (actor.role == 'team_lead' and actor.team == team):
                mode = 'manage'
            elif actor.role == 'designer' and actor.team == team:
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
        'can_toggle_focus': actor.role in ('designer', 'team_lead', 'admin'),
        # Designer/Team Lead default to Focused (their own workload first);
        # Admin's toggle doesn't filter, so it starts on All.
        'default_focus': actor.role in ('designer', 'team_lead'),
        # Deliverable-level status override — admin, or a designer with an
        # approved edit-access grant. One shared option list for both brief types.
        'can_override_status': actor.role == 'admin' or has_edit_access_grant,
        'deliverable_status_options': _DELIVERABLE_STATUS_OVERRIDE_OPTIONS,
    }


# Hourly slots, 8:00 AM through 10:00 PM, as (value, label) pairs for the
# Deliverables edit table's Time dropdown. value is 24h "HH:00" (matches
# how <input type="time"> / our own parsing expects it); label is the
# 12h display form.
DESIGN_DEADLINE_TIME_OPTIONS = [
    (f'{h:02d}:00', f'{((h - 1) % 12) + 1}:00 {"AM" if h < 12 else "PM"}')
    for h in range(8, 23)
]

_DESIGN_DEADLINE_TIME_VALUES = {v for v, _ in DESIGN_DEADLINE_TIME_OPTIONS}


def _annotate_offhour_time(deliverables):
    """The Design Deadline time dropdown only offers on-the-hour slots
    (DESIGN_DEADLINE_TIME_OPTIONS) — a deliverable whose stored time isn't
    one of those (from an older flow, or set some other way) would
    otherwise render as blank in Edit Deliverables, and an unrelated Save
    would then silently wipe the real time. Tags each such row with
    d.edit_time_extra = (value, label) so the template can inject a
    matching selected <option> and round-trip the real value untouched."""
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
    from app.modules.core.shared.models import BriefFlag, Deliverable
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    can_manage = _can_manage_deliverables(project, actor)
    can_manage_flags = _can_manage_flags(actor)
    can_skip_preproduction = _can_skip_preproduction(project, actor)
    # Passed into _build_deliverable_focus_context below so its
    # can_override_status also reflects an edit-access grant, not just
    # actor.role == 'admin' — see that function's docstring.
    has_edit_access_grant = _has_edit_access_grant(project, actor)

    # Brief Flags — one query for every open deliverable-scoped
    # flag on the project, then grouped by deliverable_id so both branches
    # below can attach "does this row/customer have open flags" without a
    # query per row. Kept as a plain dict (not a defaultdict) so Jinja's
    # `d.id in open_flags_by_deliverable_id` check works the same way
    # assigned_ids/status_by_id already do elsewhere in this file.
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
        # Needs Attention is scoped per customer —
        # each customer only sees flags on its own deliverables, computed
        # here rather than in the template so the CCM and Standard branches
        # can't drift on how "which flags belong to this customer" is worked out.
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

    deliverables = Deliverable.query.filter_by(
        project_id=project_id, project_customer_id=None
    ).order_by(Deliverable.id).all()
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
        # Same Region -> Customer grouping as the view mode (overlay_deliverables
        # above) — reusing _build_ccm_deliverable_sections keeps the customer
        # picker's options identical between view and edit, so switching
        # between them never reshuffles which customer is "first".
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
    """Bulk create/update/delete for the Deliverables editable table — one Save
    covers every change since Edit opened, committed once. Handles both brief
    types (Standard rows have no project_customer_id; C&CM rows carry one per
    customer panel, all gathered into one payload).

    Catalog picker: a C&CM row carries either an existing pick
    (deliverable_type_id) or a new name to add to the customer's catalog
    (new_type_name); rows with neither fall through to the free-text `name`.
    Catalog lookups run against types_by_customer — one query for every
    customer up front, not per row."""
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

    # Valid customer ids for this project — a row claiming a
    # project_customer_id that isn't actually one of this project's
    # customers falls back to None rather than being trusted outright.
    valid_customer_ids = {pc.id for pc in project.project_customers}

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

    # One batched fetch covering every customer referenced anywhere in this
    # payload — types_by_customer[customer_id] is a plain list, looked up
    # by id or by name (case-insensitive) in memory below, never re-queried
    # per row. Also doubles as ownership validation: a deliverable_type_id
    # the client sends only counts as a match if it's actually in this
    # customer's own catalog.
    row_customer_ids = {parse_customer_id(r.get('project_customer_id')) for r in rows}
    row_customer_ids.discard(None)
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
        design_deadline = parse_date(row.get('design_deadline'))
        design_deadline_time = parse_time(row.get('design_deadline_time'))
        teams = ','.join(row.get('teams') or [])

        resolved_type = None
        new_type_name = (row.get('new_type_name') or '').strip()
        raw_type_id = row.get('deliverable_type_id')

        if new_type_name and customer_id_for_row:
            # Reuse a same-named entry if one already exists (two rows in
            # this same save typing the identical new name) instead of
            # creating a duplicate catalog entry.
            resolved_type = lookup_type_by_name(customer_id_for_row, new_type_name)
            if not resolved_type:
                resolved_type = DeliverableType(
                    name=new_type_name,
                    client_id=project.client_id,
                    customer_id=customer_id_for_row,
                    is_custom=True,
                )
                db.session.add(resolved_type)
                # So a second row in the same payload that types the exact
                # same new name reuses this one instead of double-creating.
                types_by_customer.setdefault(customer_id_for_row, []).append(resolved_type)
            name = resolved_type.name
        elif raw_type_id and customer_id_for_row:
            try:
                resolved_type = lookup_type_by_id(customer_id_for_row, int(raw_type_id))
            except (TypeError, ValueError):
                resolved_type = None
            name = resolved_type.name if resolved_type else (row.get('name') or '').strip()
        else:
            # Legacy freeform (no catalog link yet) or Standard — name is
            # whatever the client sent, exactly as before this feature.
            name = (row.get('name') or '').strip()

        if not name:
            continue # a blank row that was never filled in — skip it rather than fail the whole save

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

    # Initial Deadline auto-follows deliverable dates in CREATE MODE only.
    # This same route also backs the
    # LIVE overlay's Save Deliverables, where Initial Deadline
    # may have been deliberately set to something a CS Lead communicated
    # externally and isn't necessarily "whatever the deliverables say" —
    # scoped to project_status == 'draft' so a live project's Save
    # Deliverables keeps behaving exactly as it always has.
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
    """Read-only computation behind Apply to Multiple's preview and confirm —
    confirm re-derives it rather than trusting the earlier preview, so a save
    landing in between can't leave it writing against stale matches.

    Three queries total (source deliverables, targets' existing deliverables,
    targets' catalogs); the rest is in-memory. Returns (source_deliverables,
    per_target), per_target keyed by target ProjectCustomer.id with 'will_add',
    'already_existing', and 'missing' lists. Returns (None, None) if a source or
    target id isn't on this project."""
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
    """Read-only step of Apply to Multiple — computes what pressing Apply
    would do without writing anything, so the modal can show the matched
    count and each target customer's missing list before anything is
    committed. Requires deliverables to already be saved (enforced
    client-side in project_deliverables_card.js, which blocks opening this
    modal while there are unsaved row edits) so this always reads real,
    committed deliverables rather than in-form drafts."""
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
    """Write step of Apply to Multiple. Re-derives matches/missing from the
    database itself via _apply_multiple_compute rather than trusting the
    client's earlier preview response, so a save or another Apply landing
    in between preview and confirm can't leave this writing against stale
    matches. Every new DeliverableType/DeliverableTypeDiscipline/
    Deliverable is batched into add_all() calls and committed once — a
    project with many target customers costs the same handful of queries
    as one, not one round trip per customer or per deliverable."""
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

        # Matched — the target customer's catalog already has this name;
        # just instantiate a Deliverable against the existing type.
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

        # Missing, but selected to be created for this customer — clones
        # team/image/template from the source's own catalog entry when it
        # has one; a legacy freeform source deliverable (no linked type)
        # has nothing to clone beyond name/teams.
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

    # add_all + one commit — new_disciplines/new_deliverables reference
    # new_types by relationship object, not id, so this is safe even
    # though none of the new types have a real primary key yet;
    # SQLAlchemy resolves every FK at flush.
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
    """Who may change one deliverable's Design-phase team assignment, and
    how far. Same set as _can_manage_deliverables (admin/management/CS
    Lead/secondary CS/Project Owner) plus this team's own team lead can
    set it to anyone on the team, or clear it. A plain designer never
    reaches this — see assign_deliverable_team()'s self_toggle branch,
    which is a separate, narrower path that can only ever touch the
    caller's own assignment, never a teammate's."""
    if _can_manage_deliverables(project, actor):
        return True
    if actor.role == 'team_lead' and actor.team == team:
        return True
    return False


@project_overlay_bp.route('/projects/<int:project_id>/overlay/deliverables/assign', methods=['POST'])
@login_required
def assign_deliverable_team(project_id):
    """Design-phase team assignment for the Deliverables roster's Team
    column. The roster shows which teams a deliverable NEEDS, but
    DeliverableAssignment had no write path in the overlay (the old detail
    page had this, the overlay never got it back). Two distinct paths:

    - self_toggle: a plain designer's one-click claim/release on their own
      team. Always re-reads the current DB state and only ever touches a
      row where designer_id is already the caller's own id (or creates a
      fresh one) — never overwrites a teammate's assignment, regardless of
      what the client's last-rendered state claimed.
    - designer_id (manage mode, possibly None to clear): CS/Admin/
      Management/Project Owner, or this team's own team lead, setting it
      to anyone on the team, reassigning, or clearing it outright.

    Separate from project_preproduction's assign_stream() — that one
    governs who does the LATER Pre-Production 2D/3D/Technical stream work
    (each stream independently assignable/reassignable there too — see the
    comment above assign_stream()); this one governs
    who's actually doing the EARLIER Design-phase work a deliverable's
    2D/3D/Technical tags say it needs. The same DeliverableAssignment row
    carries straight through from Design into Pre-Production for a given
    team (see assign_stream()'s docstring), so this route is what seeds it
    — assign_stream() just picks up from wherever this one left off, or
    fills it in if Design left it unassigned."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import Deliverable, DeliverableAssignment, User
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    data = request.get_json(silent=True) or {}
    deliverable_id = data.get('deliverable_id')
    # Normalized defensively — the template always renders a canonical
    # data-team attribute now (see _needed_teams()), but this keeps a
    # stray '2d'/'technical' from a stale cached page or a direct API
    # call from silently creating a second, differently-cased
    # DeliverableAssignment row for the same team.
    team = _canonical_team(data.get('team'))
    deliverable = Deliverable.query.get(deliverable_id) if deliverable_id else None
    if not deliverable or deliverable.project_id != project_id or not team:
        return jsonify({'success': False, 'error': 'Could not find that deliverable.'}), 400

    existing = DeliverableAssignment.query.filter_by(
        deliverable_id=deliverable.id, team=team
    ).first()

    if data.get('self_toggle'):
        if actor.role != 'designer' or actor.team != team:
            return jsonify({'success': False, 'error': 'You do not have permission to assign this.'}), 403
        if existing and existing.designer_id == actor.id:
            db.session.delete(existing)
            db.session.commit()
            log_activity('deliverable_unassigned',
                         f'{actor.name} removed themself from {team} on "{deliverable.name}" ({project.name})',
                         user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)
            return jsonify({'success': True, 'designer_id': None})
        if existing:
            # Someone else already claimed it since this button last
            # rendered — self_toggle can never steal another designer's
            # assignment, only ever the caller's own.
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
    if not target or target.role not in ('designer', 'team_lead') or target.team != team:
        return jsonify({'success': False, 'error': f'That person is not on the {team} team.'}), 400

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
    """
    Assigns/reassigns the Project Owner. Gating: Admin, Management, Project's CS lead or the Project Owner themselves.
    
    """
    from app.modules.core.shared.models import Project, User
    from app.modules.core.shared.extensions import db
    from flask import request, jsonify, session
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.services.notifications import create_notification

    project = Project.query.get_or_404(project_id)

    emulating_id = session.get('emulating_user_id')
    actor = User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    new_owner_id = request.form.get('user_id', type=int)
    if not new_owner_id:
        return jsonify({'success': False, 'error': 'Please select a Project Owner.'}), 400

    is_self_claim = (actor.role == 'project_owner' and new_owner_id == actor.id)

    if actor.role not in ('admin', 'management') and actor.id != project.cs_lead_id and not is_self_claim:
        return jsonify({'success': False, 'error': 'You are lacking permissions to perform this action.'}), 400

    new_owner = User.query.get(new_owner_id)
    if not new_owner or new_owner.role != 'project_owner':
        return jsonify({'success': False, 'error': 'Selected user is not a Project Owner'}), 400

    previous_owner = project.project_owner
    project.project_owner_id = new_owner.id
    db.session.commit()

    # Skip the you've been assigned notification when it's a self-claim

    if new_owner.id != actor.id:
        create_notification(
            recipient=new_owner,
            message=f'You have been assigned as Project Owner on "{project.name}" by {actor.name}.',
            notification_type='project_owner_assigned',
            project=project,
            triggered_by=actor,
        )

    log_activity (
        'project_owner_assigned',
        f'{actor.name} assigned {new_owner.name} as Project Owner on "{project.name}"' + (f' (previously {previous_owner.name})' if previous_owner else ''),
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id       
    )

    return jsonify({'success': True, 'owner_name': new_owner.name})


# ── Details tab person-assignment routes ──
# reassign_cs_lead / add_secondary_cs / remove_secondary_cs / assign_concept_kv
# / assign_lead — project_details_card.js POSTs to these URLs. They return JSON
# errors (never abort()), since the card reads every response as JSON.
@project_overlay_bp.route('/projects/<int:project_id>/reassign-cs-lead', methods=['POST'])
@login_required
def reassign_cs_lead(project_id):
    """CS Lead picker at the top of the Details tab. Admin/management only — a
    real ownership change."""
    from app.modules.core.shared.models import User
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.services.notifications import create_notification

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    if actor.role not in ('admin', 'management'):
        return jsonify({'success': False, 'error': 'Only admin/management can reassign a CS lead.'}), 403

    new_cs_lead_id = (request.get_json(silent=True) or {}).get('new_cs_lead_id')
    if not new_cs_lead_id:
        return jsonify({'success': False, 'error': 'A new CS lead is required.'}), 400

    new_cs_lead = User.query.get(int(new_cs_lead_id))
    if not new_cs_lead or new_cs_lead.role != 'cs':
        return jsonify({'success': False, 'error': 'CS lead not found.'}), 404

    previous_cs_lead = project.cs_lead
    project.cs_lead_id = new_cs_lead.id
    db.session.commit()

    create_notification(
        recipient=new_cs_lead,
        message=f'You have been assigned as CS lead on "{project.name}" by {actor.name}.',
        notification_type='cs_lead_reassigned',
        project=project,
        triggered_by=actor,
    )
    if previous_cs_lead and previous_cs_lead.id != new_cs_lead.id:
        create_notification(
            recipient=previous_cs_lead,
            message=f'{new_cs_lead.name} has taken over as CS lead on "{project.name}" (reassigned by {actor.name}).',
            notification_type='cs_lead_reassigned',
            project=project,
            triggered_by=actor,
        )

    log_activity(
        'cs_lead_reassigned',
        f'{actor.name} reassigned CS lead on "{project.name}" to {new_cs_lead.name}'
        + (f' (previously {previous_cs_lead.name})' if previous_cs_lead else ''),
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id
    )
    return jsonify({'success': True})


@project_overlay_bp.route('/projects/<int:project_id>/secondary-cs', methods=['POST'])
@login_required
def add_secondary_cs(project_id):
    """Add a secondary CS. Permission matches _build_details_context's
    can_manage_cs exactly (admin/management, or this project's own CS
    Lead) — NOT the old projects_detail.py version of this route, which
    gated on role_required('admin','cs','management') but then rejected
    any non-lead 'management' user in the body anyway (role_required said
    yes, the manual check said no). The template's picker/remove buttons
    are gated on can_manage_cs today, so the backend needs to agree with
    that gate exactly, not the old file's inconsistent one."""
    from app.modules.core.shared.models import User, ProjectSecondaryCS
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    if actor.role not in ('admin', 'management') and actor.id != project.cs_lead_id:
        return jsonify({'success': False, 'error': 'You do not have permission to add a secondary CS.'}), 403

    user_id = request.form.get('user_id', type=int)
    if not user_id:
        return jsonify({'success': False, 'error': 'Please select a CS member.'}), 400

    if user_id == project.cs_lead_id:
        return jsonify({'success': False, 'error': 'The CS lead is already the primary CS on this project.'}), 400

    user = User.query.get(user_id)
    if not user or user.role not in ('cs', 'admin', 'management'):
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

    if actor.role not in ('admin', 'management') and actor.id != project.cs_lead_id:
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
    """Concept & KV Designer picker on the Details tab
    (avatar_picker('concept-kv-designer-picker', ...)). Admin/management
    can assign anyone; designer/team_lead can only self-claim — matches
    can_manage_concept_kv_full / can_self_claim_concept_kv in
    _build_details_context, which already gates whether this picker even
    renders and what options it offers."""
    from app.modules.core.shared.models import User
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity
    from app.modules.core.shared.services.notifications import notify_designer_of_concept_kv_assignment

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()

    full_control = actor.role in ('admin', 'management')
    self_claim_only = actor.role in ('designer', 'team_lead')
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
    """Design Leads per-team picker on the Details tab. Permission keys off the
    target: picking yourself is always allowed for your own team (fill or take
    over a slot); picking a specific teammate is a transfer, allowed only for the
    current lead (or admin/management).

    ProjectDesigner has a DB unique constraint on (project_id, team) — delete the
    existing row and flush before inserting, or the INSERT raises a
    UniqueViolation instead of replacing it."""
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

    if actor.role in ('designer', 'team_lead') and actor.team != team:
        return jsonify({'success': False, 'error': 'You can only assign yourself to your own team.'}), 403

    target_id = int(raw_target_id) if raw_target_id else actor.id
    is_self = (target_id == actor.id)

    current_assignment = ProjectDesigner.query.filter_by(project_id=project.id, team=team).first()
    previous_designer = current_assignment.designer if current_assignment else None

    if not is_self:
        # Handing the lead role to someone ELSE — only the current lead
        # may do this, unless the actor is admin/management.
        if actor.role not in ('admin', 'management'):
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
        # Self-claim/takeover — always allowed for the actor's own team,
        # whether the slot is empty or currently held by someone else.
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
