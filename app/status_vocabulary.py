"""
app/status_vocabulary.py

The new three-tier status vocabulary from the Detail+Briefing overlay rework
— see Projects Redesign Architecture.md §4. These are read-only DERIVATION
functions: given a model instance, return the (label, css_modifier) pair a
template renders as a status pill (see app/static/css/shared.css's
.status-pill / .status-pill--<modifier> classes). They don't write anything —
actual status transitions still happen through app/status_tracking.py's
funnel and record_deliverable_status()/record_project_status(); this module
only translates the resulting raw values into the new vocabulary for display,
in one place, so every surface (Projects list, later the overlay + roster)
agrees.
"""
from app.models import ProjectPosmChannel


# ── Tier 1: Deliverable status (every deliverable, both brief types) ───────
# "Unassigned" became "Briefed" during the M2 Figma pass (30 Jul 2026) — a
# deliverable just reads Briefed until an explicit "Start" action flips
# Deliverable.status to 'in_progress'. That button doesn't exist yet (lands
# with the M6 roster), so no real deliverable has this raw value today —
# every fresh deliverable sits at 'in_queue' until a designer submits it.
def derive_deliverable_status(deliverable):
    """Returns (label, css_modifier) for one Deliverable row."""
    raw = deliverable.status

    if raw in ('revision_in_queue', 'internal_revision', 'revision_in_progress'):
        return ('In Revision', 'lavender')
    if raw == 'internal_review':
        return ('In Review', 'canary')
    if raw == 'submitted_to_client':
        return ('Submitted to Client', 'sage')
    if raw == 'approved':
        return _post_approval_deliverable_status(deliverable)
    if raw == 'in_progress':
        return ('In Progress', 'coral')
    # raw == 'in_queue' (or the unused legacy column default)
    return ('Briefed', 'sky')


def _post_approval_deliverable_status(deliverable):
    """
    Once design-approved, a deliverable's pill keeps advancing through the
    pre-production layer (needs_technical/needs_artwork + their own
    technical_status/artwork_status — Projects Redesign Architecture.md §5).
    Placeholder vocabulary for those two columns (locked 30 Jul 2026, to be
    refined when M8 designs the real Pre-Production submission flow): NULL/
    anything else = still in progress, 'approved' = that stream is done.
    """
    needs_any = deliverable.needs_technical or deliverable.needs_artwork
    if not needs_any:
        return ('Client Approved', 'clover')

    technical_done = (not deliverable.needs_technical) or deliverable.technical_status == 'approved'
    artwork_done = (not deliverable.needs_artwork) or deliverable.artwork_status == 'approved'

    if technical_done and artwork_done:
        return ('Handed to Production', 'clover')
    return ('Pre-Production', 'oak')


# ── Shared stage mapping (Tier 2 + the per-channel check Tier 3 uses) ──────
# Pre-Production / Handed to Production don't have real transitions writing
# to project_status or ProjectPosmChannel.status yet (M6-M8 work) — mapped
# here for completeness but won't appear on real data until then. Every
# existing raw value today falls into 'In Design' or 'Client Approved'.
def _pipeline_stage_for(raw_status):
    if raw_status == 'approved':
        return ('Client Approved', 'clover')
    if raw_status == 'pre_production':        # not yet written anywhere — M8
        return ('Pre-Production', 'oak')
    if raw_status == 'handed_to_production':   # not yet written anywhere — M8
        return ('Handed to Production', 'clover')
    return ('In Design', 'coral')


# ── Tier 2: Pipeline status (Standard project-level) ───────────────────────
# On Hold / Cancelled are orthogonal to the pipeline (§4) — checked first,
# ahead of the underlying stage.
def derive_pipeline_status(project):
    """Returns (label, css_modifier) for a Standard project's Status column."""
    if project.cancelled_at is not None:
        return ('Cancelled', 'salmon')
    if project.project_status == 'on_hold':
        return ('On Hold', 'poppy')
    return _pipeline_stage_for(project.project_status)


# ── Tier 3: C&CM aggregate (C&CM project overall) ───────────────────────────
# Computed from every channel — see the M1 finding in Projects Redesign
# Architecture.md §C: the real per-customer/per-region pipeline lives on
# ProjectPosmChannel, not ProjectCustomer.status (which is only ever
# 'briefed' in the real code).
def derive_ccm_aggregate_status(project):
    """Returns (label, css_modifier) for a C&CM project's Status column."""
    if project.cancelled_at is not None:
        return ('Cancelled', 'salmon')
    if project.project_status == 'on_hold':
        return ('On Hold', 'poppy')

    channels = project.posm_channels
    if not channels:
        return ('Briefed', 'sky')

    # "Design Completed" per the architecture doc means every customer
    # reached Handed to Production — that stage doesn't exist in real
    # channel data yet (M8), so 'approved' (Client Approved) is today's
    # practical stand-in for "this channel's design work is done."
    if all(c.status == 'approved' for c in channels):
        return ('Design Completed', 'clover')
    if any(c.status != 'in_queue' for c in channels):
        return ('In Progress', 'coral')
    return ('Briefed', 'sky')


def derive_project_status(project):
    """The Projects-list-page Status column/filter value for one project —
    Pipeline status for Standard, the C&CM aggregate for C&CM."""
    if project.brief_type == 'ccm':
        return derive_ccm_aggregate_status(project)
    return derive_pipeline_status(project)


def derive_customer_pipeline_status(project_customer):
    """
    Returns (label, css_modifier) for one C&CM customer's expand row. Real
    per-customer/per-region tracking lives on ProjectPosmChannel: UAE
    customers get their own channel (posm_customer_id set to that customer);
    Gulf customers share one channel per country/region (posm_customer_id
    NULL) — so multiple customers under the same Gulf country resolve to
    the same channel, and therefore the same status. Mirrors the matching
    logic used in the M1 workflow_status backfill and in approve_submission().
    """
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