"""
Read-only mapping from raw status values to the (label, css_modifier) pair a
template renders as a status pill (.status-pill--<modifier> in shared.css).
The one place raw statuses become display labels. Writes go through
services/status_tracking.py.

Deliverables and projects share one shape: In Design -> Pre-Production ->
Handed to Production, with Cancelled / On Hold checked first.
"""
from app.modules.core.shared.models import ProjectPosmChannel


# ── Deliverable status (every deliverable, both brief types) ───────────────
def derive_deliverable_status(deliverable):
    """(label, css_modifier) for one Deliverable. Every status before
    'approved' reads "In Design"."""
    if deliverable.status == 'approved':
        return _post_approval_deliverable_status(deliverable)
    return ('In Design', 'coral')


def derive_preproduction_needs(deliverable):
    """(needs_2d, needs_3d, needs_technical) from the design teams on the
    deliverable (its type's disciplines, else its `teams` string). Pure;
    callers store the result when a deliverable is approved."""
    if deliverable.deliverable_type and deliverable.deliverable_type.disciplines:
        teams = {disc.team for disc in deliverable.deliverable_type.disciplines}
    else:
        teams = {t.strip() for t in (deliverable.teams or '').split(',') if t.strip()}
    return '2D' in teams, '3D' in teams, 'Technical' in teams


def _post_approval_deliverable_status(deliverable):
    """
    Pre-Production until every needed 2D/3D/Technical stream is 'approved',
    then Handed to Production. Needing no stream means Handed to Production.
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


# ── Per-channel stage mapping (derive_customer_pipeline_status only) ───────
# ProjectPosmChannel.status is independent and does not feed the project
# pill. No code writes 'briefed' or 'pre_production' to a channel, so those
# branches are unreachable.
def _pipeline_stage_for(raw_status):
    if raw_status in ('approved', 'pre_production'):
        return ('Pre-Production', 'oak')
    if raw_status == 'handed_to_production':
        return ('Handed to Production', 'clover')
    if raw_status == 'briefed':
        return ('Briefed', 'sky')
    # Split out from In Design: design is done and CS is waiting on the
    # client. derive_deliverable_status() does not split it; it reads In Design.
    if raw_status == 'submitted_to_client':
        return ('Submitted to Client', 'sage')
    return ('In Design', 'coral')


# ── Project status (same rule for Standard and C&CM) ───────────────────────
# Cancelled and On Hold win; Briefed holds until someone clicks Start. After
# that the pill rolls up every deliverable on the project:
#   - In Design: any deliverable still reads In Design.
#   - Pre-Production: none reads In Design (raw project_status 'approved').
#   - Handed to Production: all read Handed to Production (the Projects
#     list's Design Completed tab).
# status_tracking.sync_project_pipeline_status() writes project_status by
# this same rule.
def derive_project_status(project):
    """(label, css_modifier) for a project's status pill."""
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
    (label, css_modifier) for one C&CM customer's expand row. UAE customers
    have their own channel; Gulf customers share one channel per country
    (posm_customer_id NULL), so they share a status. Cancelled is checked
    first, so cancelling never touches the channel's status.
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