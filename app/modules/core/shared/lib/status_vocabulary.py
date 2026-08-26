"""
Status vocabulary: read-only DERIVATION functions that turn a model
instance into the (label, css_modifier) pair a template renders as a status
pill (see shared.css's .status-pill / .status-pill--<modifier>). Nothing
here writes; status transitions happen through the status_tracking funnel
(record_deliverable_status / record_project_status /
sync_project_pipeline_status). This module is the single place that
translates raw status values into display vocabulary, so every surface
agrees.

Deliverable and project pills share one 3-stage shape:
In Design -> Pre-Production -> Handed to Production, with On Hold and
Cancelled orthogonal and checked first. Every pre-approval raw status reads
as "In Design"; a deliverable reads Handed to Production once every
Pre-Production stream it needs is approved (immediately on approval if it
needs none). A project pill is a live roll-up of its deliverables under the
same rule for Standard and C&CM briefs alike.

_pipeline_stage_for() / derive_customer_pipeline_status() render the same
vocabulary for a C&CM customer's expand row, reading the independent
ProjectPosmChannel.status field.
"""
from app.modules.core.shared.models import ProjectPosmChannel


# ── Deliverable status (every deliverable, both brief types) ───────────────
def derive_deliverable_status(deliverable):
    """Returns (label, css_modifier) for one Deliverable row. Every
    pre-approval raw value (in_queue/in_progress/internal_review/
    revision_in_queue/internal_revision/revision_in_progress/
    submitted_to_client) reads as one "In Design" label; only 'approved'
    branches into the post-approval Pre-Production/Handed to Production
    split below."""
    if deliverable.status == 'approved':
        return _post_approval_deliverable_status(deliverable)
    return ('In Design', 'coral')


def derive_preproduction_needs(deliverable):
    """Auto-determines which Pre-Production release streams a deliverable
    needs, from whichever design teams were already attached to it — no
    manual Project Owner flagging step. 2D/3D/Technical are three fully
    independent streams (each with its own assignment/status/flag cycle),
    matching how Design already treats them as three separate teams. Pure
    function — called at the moment a deliverable
    reaches 'approved' (Client Approval or Skip to Pre-Production), not
    stored as its own status.
    Returns (needs_2d, needs_3d, needs_technical)."""
    if deliverable.deliverable_type and deliverable.deliverable_type.disciplines:
        teams = {disc.team for disc in deliverable.deliverable_type.disciplines}
    else:
        teams = {t.strip() for t in (deliverable.teams or '').split(',') if t.strip()}
    return '2D' in teams, '3D' in teams, 'Technical' in teams


def _post_approval_deliverable_status(deliverable):
    """
    Once design-approved, a deliverable's pill keeps advancing through the
    pre-production layer — 2D/3D/Technical are three independent streams,
    each with its own needs_*/*_status pair. NULL/anything else = still in
    progress, 'approved' = that stream is done — a deliverable only reaches
    Handed to Production once every stream it actually needs is approved.

    A deliverable that needs NO Pre-Production stream at all reads Handed to
    Production immediately on approval — there is nothing left for it to do.
    """
    needs_any = deliverable.needs_2d or deliverable.needs_3d or deliverable.needs_technical
    if not needs_any:
        return ('Handed to Production', 'clover')

    done_2d = (not deliverable.needs_2d) or deliverable.status_2d == 'approved'
    done_3d = (not deliverable.needs_3d) or deliverable.status_3d == 'approved'
    done_technical = (not deliverable.needs_technical) or deliverable.technical_status == 'approved'

    if done_2d and done_3d and done_technical:
        return ('Handed to Production', 'clover')
    return ('Pre-Production', 'oak')


# ── Per-channel stage mapping — used only by derive_customer_pipeline_status.
# C&CM's per-customer expand rows read ProjectPosmChannel.status, a
# genuinely independent per-channel field that does not feed the overall
# project pill. It renders through the same label vocabulary as everywhere
# else: 'approved' reads "Pre-Production" here, same as 'pre_production'.
# The 'briefed'/'pre_production' branches are dead for a real channel
# (channels never seed at or advance to either raw value) — kept for
# completeness.
def _pipeline_stage_for(raw_status):
    if raw_status in ('approved', 'pre_production'):
        return ('Pre-Production', 'oak')
    if raw_status == 'handed_to_production':
        return ('Handed to Production', 'clover')
    if raw_status == 'briefed':
        return ('Briefed', 'sky')
    # 'Submitted to Client' is kept distinct from the 'In Design' catch-all:
    # 'In Design' means the design team still has work to do, while
    # 'Submitted to Client' means design is done and CS is waiting on an
    # external reply — different people, different next action. Uses the
    # same label + colour derive_deliverable_status() uses for this exact
    # raw value, so the two agree.
    if raw_status == 'submitted_to_client':
        return ('Submitted to Client', 'sage')
    return ('In Design', 'coral')


# ── Project status — one unified rule for both brief types ─────────────────
# On Hold / Cancelled are orthogonal, checked first ahead of the underlying
# stage. Briefed is the explicit Start Project gate — a project sits at
# Briefed until someone clicks Start.
#
# Past Briefed, the pill is a pure live roll-up of the project's own
# deliverables — the same rule for Standard and C&CM alike, computed across
# every deliverable on the project regardless of which C&CM customer/channel
# it's under. Nothing else decides it (not Submit to Client, not Concept/KV
# approval, not a per-channel cascade) — see status_tracking's
# sync_project_pipeline_status(), the one place that writes
# project.project_status based on this rule, called after every action that
# can change a deliverable's own label.
#
# Same 3-stage shape as the deliverable pill:
#   - In Design: at least one deliverable hasn't moved past In Design yet.
#   - Pre-Production: every deliverable has moved past In Design (each one's
#     own label is Pre-Production or Handed to Production) — the raw
#     project_status value here is 'approved'.
#   - Handed to Production: every deliverable itself reads Handed to
#     Production. This is also what the Projects list's Design Completed tab
#     shows (project_list.py).
def derive_project_status(project):
    """Returns (label, css_modifier) for a project's Status column/pill —
    same rule regardless of brief_type."""
    if project.cancelled_at is not None:
        return ('Cancelled', 'salmon')
    if project.project_status == 'on_hold':
        return ('On Hold', 'poppy')
    if project.project_status == 'briefed':
        return ('Briefed', 'sky')

    deliverables = project.project_deliverables
    if not deliverables:
        return ('In Design', 'coral')

    labels = [derive_deliverable_status(d)[0] for d in deliverables]
    if all(label == 'Handed to Production' for label in labels):
        return ('Handed to Production', 'clover')
    if all(label != 'In Design' for label in labels):
        return ('Pre-Production', 'oak')
    return ('In Design', 'coral')


def derive_customer_pipeline_status(project_customer):
    """
    Returns (label, css_modifier) for one C&CM customer's expand row. Real
    per-customer/per-region tracking lives on ProjectPosmChannel: UAE
    customers get their own channel (posm_customer_id set to that customer);
    Gulf customers share one channel per country/region (posm_customer_id
    NULL) — so multiple customers under the same Gulf country resolve to
    the same channel, and therefore the same status.

    The cancelled check is the same shape as derive_project_status()'s
    cancelled_at check above, and
    for the same reason: cancelled overrides whatever the underlying
    pipeline stage was, checked first, ahead of the channel lookup, so
    cancelling never needs to touch (and reactivating never needs to
    restore) the channel's actual status.
    """
    if project_customer.cancelled:
        return ('Cancelled', 'salmon')

    channel = ProjectPosmChannel.query.filter_by(
        project_id=project_customer.project_id,
        posm_customer_id=project_customer.id
    ).first()
    if not channel:
        channel = ProjectPosmChannel.query.filter_by(
            project_id=project_customer.project_id,
            posm_country=project_customer.customer.region,
            posm_customer_id=None
        ).first()
    if not channel:
        return ('Briefed', 'sky')
    return _pipeline_stage_for(channel.status)