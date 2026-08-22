# app/status_tracking.py
#
# Single funnel for every project / customer / deliverable status change.
# Replaces raw `.project_status = X` / `.status = X` assignments so every
# transition is captured in the matching *StatusLog table (app/models) —
# one place instead of scattered across every route that used to set the
# field directly.
#
# Each public function still sets the actual status column itself, so a
# call site just swaps the raw assignment for the matching wrapper call —
# no extra step, no risk of forgetting to also update the field.
#
# None of these call db.session.commit() — that stays the caller's job,
# same as before, usually alongside other changes in the same transaction.

from datetime import datetime


def _record_status_change(entity, new_status, actor, log_cls, fk_field):
    """Internal — closes the entity's current open log row (if any) and
    opens a new one. Shared by the three public wrappers below so the
    open/close bookkeeping only exists in one place."""
    from app import db

    now = datetime.utcnow()

    open_row = log_cls.query.filter_by(**{fk_field: entity.id}, ended_at=None).first()
    if open_row:
        open_row.ended_at = now

    db.session.add(log_cls(
        **{fk_field: entity.id},
        status=new_status,
        started_at=now,
        changed_by_id=actor.id if actor else None
    ))


def record_project_status(project, new_status, actor):
    """
    Time-tracking note (13 Jul 2026): this function's ProjectStatusLog
    rows (started_at/ended_at per status) are the ONLY thing the
    project/deliverable hours feature reads — see
    app/time_tracking_logic.py. There is no separate hours-accumulator
    write here; hours are recomputed from this log history on demand, so
    there's exactly one source of truth for "how long was this project in
    status X" rather than a running counter that could drift from it.

    (Historical note: earlier the same day, a live hours_accumulated/
    timer_started_at accumulator WAS spliced in right here, re-wiring
    logic that used to live dead/unreachable in
    app/routes/projects_old.py's update_status route. It used plain
    wall-clock hours and a narrow 2-status "active" set. Per Ezekiel's
    fuller spec later the same day — business hours only, weekend
    discard rule, per-status breakdown for a new drill-down page — that
    approach was superseded by the StatusLog-derived computation in
    time_tracking_logic.py before it ever went live, so it was removed
    again rather than left running alongside the new logic. The
    Project.hours_accumulated/timer_started_at columns are no longer
    written to by anything; left in place on the model, unused.)
    """
    from app.models import ProjectStatusLog
    _record_status_change(project, new_status, actor, ProjectStatusLog, 'project_id')
    project.project_status = new_status


def record_customer_status(customer, new_status, actor):
    from app.models import ProjectCustomerStatusLog
    _record_status_change(customer, new_status, actor, ProjectCustomerStatusLog, 'project_customer_id')
    customer.status = new_status


def record_deliverable_status(deliverable, new_status, actor):
    from app.models import DeliverableStatusLog
    _record_status_change(deliverable, new_status, actor, DeliverableStatusLog, 'deliverable_id')
    deliverable.status = new_status


def sync_project_pipeline_status(project, actor):
    """
    Project status simplification (22 Aug 2026, per Ezekiel) — the project
    pill is now a pure, live roll-up of its deliverables, computed the same
    way for Standard AND C&CM (one project-wide check across every
    deliverable regardless of which C&CM customer/channel it's under — no
    more separate per-channel aggregate for this top-level pill). Nothing
    else decides it: not the Start Project button, not Submit to Client,
    not Concept/KV approval, not the old per-channel Client Approval
    cascade — those still exist and still gate their own actions/
    notifications, but none of them write project_status directly anymore.
    This is the ONLY place that does, called after any action that can
    change what a deliverable's status_vocabulary.py label reads:
    record_deliverable_status(), a Pre-Production stream approve/flag, or
    an admin deliverable-status override.

    Deliberately a no-op for 'draft' / 'briefed' / 'on_hold' and once
    cancelled_at is set — those stay exactly what they are today (Start
    Project / Put on Hold / Cancel are still the only things that move a
    project into or out of them). Only the three deliverable-driven stages
    (In Design / Pre-Production / Handed to Production — raw values
    'in_progress' / 'approved' / 'handed_to_production', unchanged from
    before this simplification, and unchanged again by the later-same-day
    removal of "Client Approved" as the raw 'approved' value's label — see
    status_vocabulary.py — so every existing SQL filter keyed on
    project_status keeps working) are ever written here.

    Safe to call after every deliverable-affecting action, even ones that
    don't actually change anything — record_project_status() no-ops
    cleanly (still opens a fresh ProjectStatusLog row) when the target
    already matches project.project_status... actually it doesn't
    early-return, so this function checks first and skips the call
    entirely when nothing would change, same guard record_project_status's
    callers have always been expected to apply themselves.
    """
    from app.status_vocabulary import derive_deliverable_status

    if project.cancelled_at is not None or project.project_status in ('draft', 'briefed', 'on_hold'):
        return

    deliverables = project.project_deliverables
    if not deliverables:
        return

    labels = [derive_deliverable_status(d)[0] for d in deliverables]
    if all(label == 'Handed to Production' for label in labels):
        target = 'handed_to_production'
    elif all(label != 'In Design' for label in labels):
        target = 'approved'
    else:
        target = 'in_progress'

    if project.project_status != target:
        record_project_status(project, target, actor)


# ── Read helpers — "when did this status last change" ──────────────────
# Pure reads, companions to the *StatusLog tables the functions above
# write to — nothing here writes anything. Added 22 Aug 2026 (per Ezekiel:
# "All status changes need to be time stamped") to surface the started_at
# data these tables already capture in the UI next to status pills,
# rather than adding any new tracking. Note this is the raw column's own
# started_at, not "since the derived pill label started reading this" —
# a deliverable can cycle through several raw Submissions-flow statuses
# (internal_review/revision_in_queue/etc.) that all collapse into the same
# "In Design" label, each opening a fresh log row, so this answers "when
# did the status last change" rather than "how long has the pill shown
# what it shows now". That's the literal ask; a true label-level rollup
# timestamp would be a separate, bigger feature.

def project_status_started_at(project):
    """started_at of `project`'s currently-open ProjectStatusLog row.
    None if nothing has ever been logged for it (pre-dates this table)."""
    from app.models import ProjectStatusLog
    row = ProjectStatusLog.query.filter_by(project_id=project.id, ended_at=None).first()
    return row.started_at if row else None


def deliverable_status_started_at(deliverable):
    """Same as project_status_started_at, for one Deliverable. Prefer
    bulk_deliverable_status_started_at when looking this up for more than
    one deliverable at a time — this issues one query per call."""
    from app.models import DeliverableStatusLog
    row = DeliverableStatusLog.query.filter_by(deliverable_id=deliverable.id, ended_at=None).first()
    return row.started_at if row else None


def bulk_deliverable_status_started_at(deliverable_ids):
    """Same data as deliverable_status_started_at, for many deliverables
    in one query — {deliverable_id: started_at}. A deliverable with no
    log row yet just doesn't appear as a key."""
    from app.models import DeliverableStatusLog
    if not deliverable_ids:
        return {}
    rows = DeliverableStatusLog.query.filter(
        DeliverableStatusLog.deliverable_id.in_(deliverable_ids),
        DeliverableStatusLog.ended_at.is_(None)
    ).all()
    return {row.deliverable_id: row.started_at for row in rows}


def bulk_project_status_started_at(project_ids):
    """Same as bulk_deliverable_status_started_at, for projects — used by
    the Projects list so it doesn't run one query per row."""
    from app.models import ProjectStatusLog
    if not project_ids:
        return {}
    rows = ProjectStatusLog.query.filter(
        ProjectStatusLog.project_id.in_(project_ids),
        ProjectStatusLog.ended_at.is_(None)
    ).all()
    return {row.project_id: row.started_at for row in rows}


# ── Read helpers — "when was this last client-approved" ─────────────────
# Added 22 Aug 2026, later the same day (per Ezekiel, dropping "Client
# Approved" as its own pill stage): "ensure anything that ever does go to
# preproduction gets its client approved time stamped for the future
# dashboard updates. If something gets reverted, the timestamp for the
# previous approval stays and an addition is added."
#
# Different from *_status_started_at above on purpose. Those answer "since
# when has the CURRENT status been true" — fine for a deliverable, whose
# raw status stays 'approved' all the way through Pre-Production AND
# Handed to Production (the label split between those two is driven by
# the stream fields, not another status change), so the current open
# DeliverableStatusLog row's started_at already IS the approval moment for
# as long as that holds. It's NOT fine for a project: project_status keeps
# moving (raw 'approved' -> 'handed_to_production' is a real second
# transition, see sync_project_pipeline_status), which closes the
# 'approved' log row and opens a new one — so project_status_started_at
# would silently start answering "since handed to production" instead,
# losing the approval moment entirely once a project ships.
#
# These two instead search for the most recent log row with
# status == 'approved' specifically, whether or not that's still the
# current status. Nothing is ever overwritten or deleted to get here —
# _record_status_change() (this file, above) only ever closes a row
# (ended_at) and opens a new one, so every past approval's row and its
# started_at survives forever, exactly as asked: if an entity is later
# reverted out of 'approved' (e.g. the admin deliverable-status override's
# "In Design" option, or any future revert path built the same way,
# through record_deliverable_status()/record_project_status()) and then
# re-approved, THIS finds the new row; the previous approval's row simply
# stops being "most recent" — it isn't touched. A future dashboard that
# wants the FULL approval history (not just the latest) can run the same
# query without the .order_by().first() — every row is still sitting
# there.

def latest_client_approval_at(entity, log_cls, fk_field):
    """Internal — shared by project_client_approved_at()/
    deliverable_client_approved_at() below, same pattern
    _record_status_change() uses to share code between the project/
    deliverable wrappers. Most recent started_at across every one of
    entity's log rows where status == 'approved'; None if it's never
    been approved."""
    row = (
        log_cls.query
        .filter_by(**{fk_field: entity.id}, status='approved')
        .order_by(log_cls.started_at.desc())
        .first()
    )
    return row.started_at if row else None


def project_client_approved_at(project):
    """When `project` was last client-approved (raw project_status
    entered 'approved') — survives the project later moving on to
    'handed_to_production', unlike project_status_started_at. None if it
    never has been."""
    from app.models import ProjectStatusLog
    return latest_client_approval_at(project, ProjectStatusLog, 'project_id')


def deliverable_client_approved_at(deliverable):
    """Same as project_client_approved_at, for one Deliverable. In
    practice this usually equals deliverable_status_started_at (a
    deliverable's raw status doesn't move again after 'approved' — Pre-
    Production vs. Handed to Production is a stream-field split, not
    another status change) — they only diverge if the deliverable was
    reverted out of 'approved' and hasn't been re-approved yet, in which
    case this still remembers the earlier approval."""
    from app.models import DeliverableStatusLog
    return latest_client_approval_at(deliverable, DeliverableStatusLog, 'deliverable_id')


def bulk_project_client_approved_at(project_ids):
    """Same data as project_client_approved_at, for many projects in one
    query — {project_id: started_at}, using the MAX started_at among each
    project's 'approved' rows (equivalent to picking the latest one, just
    without N separate queries). A project never approved doesn't appear
    as a key."""
    from app import db
    from app.models import ProjectStatusLog
    if not project_ids:
        return {}
    rows = (
        db.session.query(ProjectStatusLog.project_id, db.func.max(ProjectStatusLog.started_at))
        .filter(ProjectStatusLog.project_id.in_(project_ids), ProjectStatusLog.status == 'approved')
        .group_by(ProjectStatusLog.project_id)
        .all()
    )
    return dict(rows)


def bulk_deliverable_client_approved_at(deliverable_ids):
    """Same as bulk_project_client_approved_at, for deliverables."""
    from app import db
    from app.models import DeliverableStatusLog
    if not deliverable_ids:
        return {}
    rows = (
        db.session.query(DeliverableStatusLog.deliverable_id, db.func.max(DeliverableStatusLog.started_at))
        .filter(DeliverableStatusLog.deliverable_id.in_(deliverable_ids), DeliverableStatusLog.status == 'approved')
        .group_by(DeliverableStatusLog.deliverable_id)
        .all()
    )
    return dict(rows)