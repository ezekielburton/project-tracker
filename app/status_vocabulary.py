"""
app/status_vocabulary.py

The status vocabulary from the Detail+Briefing overlay rework — see
Projects Redesign Architecture.md §4 for the original three-tier version,
and the 22 Aug 2026 simplification (per Ezekiel) that collapsed it down to
this one. These are read-only DERIVATION functions: given a model instance,
return the (label, css_modifier) pair a template renders as a status pill
(see app/static/css/shared.css's .status-pill / .status-pill--<modifier>
classes). They don't write anything — actual status transitions still
happen through app/status_tracking.py's funnel
(record_deliverable_status()/record_project_status()/
sync_project_pipeline_status()); this module only translates the resulting
raw values into the vocabulary for display, in one place, so every surface
agrees.

The simplification (22 Aug 2026, per Ezekiel): a deliverable pill now only
ever reads In Design -> Pre-Production -> Handed to Production — every
pre-approval raw status (Briefed/In Progress/In Review/In Revision/
Submitted to Client) collapses into one "In Design" label, and a
deliverable that needs no Pre-Production stream at all now reads Handed to
Production immediately on approval instead of parking at a permanent
"Client Approved". The project pill matches that exact same 3-stage shape
(same day, per Ezekiel's follow-up — "it's actually much cleaner going
from In Design -> Preproduction -> handed to production"): Briefed -> In
Design -> Pre-Production -> Handed to Production (On Hold/Cancelled still
orthogonal, checked first) — computed as a live roll-up of the project's
own deliverables (see derive_project_status below), the same rule for
Standard and C&CM alike; there is no more separate C&CM aggregate tier and
no more "Design Completed" as its own label — a project whose pill reads
Handed to Production is what the Projects list's Design Completed tab
shows (project_list.py), nothing else does. "Client Approved" is gone as a
label entirely now, everywhere — project pill, deliverable pill, AND
C&CM's per-customer expand rows (_pipeline_stage_for() below, corrected
23 Aug 2026 after it was missed in the first pass — Ezekiel: "why am I
still seeing client approved on customer channels?"). The raw 'approved'
status value still means exactly what it always did (client signed off,
ready for Pre-Production), it just no longer gets its own pill text
anywhere; see status_tracking.py's project_client_approved_at()/
deliverable_client_approved_at() for where that moment is still captured
with a timestamp, non-destructively, for future dashboard use even though
nothing displays it as its own stage anymore.

The raw underlying values these collapse FROM are unchanged and still real
— submission review/revision/approval and the Pre-Production stream cycle
still work exactly as before, this module just displays less granularity
than it used to.

_pipeline_stage_for() / derive_customer_pipeline_status() are still their
own separate TRACKING mechanism, not a display exception anymore: C&CM's
per-customer expand rows (project_list.py) read ProjectPosmChannel.status,
a genuinely independent per-channel field that has never fed the overall
project pill and still doesn't — that per-customer state-tracking was
deliberately left alone and still is. But the VOCABULARY it displays
through now matches everywhere else — no surface anywhere shows "Client
Approved" any longer.
"""
from app.models import ProjectPosmChannel


# ── Deliverable status (every deliverable, both brief types) ───────────────
def derive_deliverable_status(deliverable):
    """Returns (label, css_modifier) for one Deliverable row. Every
    pre-approval raw value (in_queue/in_progress/internal_review/
    revision_in_queue/internal_revision/revision_in_progress/
    submitted_to_client — the real Submissions-flow states, still written
    exactly as before) reads as one "In Design" label now; only 'approved'
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
    matching how Design already treats them as three separate teams — 2D
    and 3D used to collapse into one combined "artwork" stream; that
    collapse is gone. Pure function — called at the moment a deliverable
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
    pre-production layer — 2D/3D/Technical are three independent streams
    now, each with its own needs_*/*_status pair (2D and 3D used to share
    one combined needs_artwork/artwork_status pair; that collapse is gone).
    NULL/anything else = still in progress, 'approved' = that stream is
    done — a deliverable only reaches Handed to Production once every
    stream it actually needs is approved.

    A deliverable that needs NO Pre-Production stream at all used to park
    permanently at "Client Approved" (nothing left to do, but nothing to
    call it either). Simplified (22 Aug 2026, per Ezekiel) — "Client
    Approved" was dropped from the deliverable's 3-stage flow entirely, so
    approval alone now reads as done: Handed to Production immediately,
    same as if it had needed streams and every one of them just got
    approved.
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


# ── Per-channel stage mapping — used only by derive_customer_pipeline_status
# now (22 Aug 2026 simplification, per Ezekiel) — the overall project pill
# above no longer reads ProjectPosmChannel.status at all, but C&CM's
# per-customer expand rows still do, unchanged: that per-channel state
# tracking is genuinely independent and stays exactly as it was. The
# LABEL VOCABULARY it renders through does not get its own exception,
# though (fixed 23 Aug 2026, per Ezekiel — the per-customer table was
# still showing "Client Approved" pills after that label was supposed to
# be gone everywhere): 'approved' now reads "Pre-Production" here too,
# same text/colour as 'pre_production' below and as the project/
# deliverable pills — one vocabulary, no surface left showing the old
# label. 'briefed'/'pre_production' branches are dead for a real channel
# (channels never seed at or advance to either raw value) — kept for
# completeness/history, same as before this simplification.
def _pipeline_stage_for(raw_status):
    if raw_status in ('approved', 'pre_production'):
        return ('Pre-Production', 'oak')
    if raw_status == 'handed_to_production':
        return ('Handed to Production', 'clover')
    if raw_status == 'briefed':
        return ('Briefed', 'sky')
    # 'Submitted to Client' split out from the 'In Design' catch-all
    # (M10, 20 Aug 2026, per Ezekiel) — the dashboard's Next Action work
    # surfaced that collapsing these together hid a real distinction:
    # 'In Design' means the design team still has work to do, while
    # 'Submitted to Client' means design is done and CS is waiting on an
    # external reply — different people, different next action. Uses the
    # same label + colour Tier 1's derive_deliverable_status() already
    # uses for this exact raw value, so the two tiers agree.
    if raw_status == 'submitted_to_client':
        return ('Submitted to Client', 'sage')
    return ('In Design', 'coral')


# ── Project status — one unified rule for both brief types ─────────────────
# On Hold / Cancelled are orthogonal — checked first, ahead of the
# underlying stage, same as always. Briefed is still the explicit Start
# Project gate (untouched by this simplification — a project sits at
# Briefed until someone clicks Start, exactly as before).
#
# Past Briefed, the pill is a pure live roll-up of the project's own
# deliverables (22 Aug 2026 simplification, per Ezekiel) — the SAME rule
# for Standard and C&CM alike, computed across every deliverable on the
# project regardless of which C&CM customer/channel it's under. Nothing
# else decides it (not Submit to Client, not Concept/KV approval, not a
# per-channel cascade) — see app/status_tracking.py's
# sync_project_pipeline_status(), the one place that writes
# project.project_status based on this rule, called after every action
# that can change a deliverable's own label.
#
# Same 3-stage shape as the deliverable pill now (22 Aug 2026, later the
# same day, per Ezekiel — "Client Approved" removed as its own stage
# entirely, "much cleaner going from In Design -> Preproduction -> handed
# to production"):
#   - In Design: at least one deliverable hasn't moved past In Design yet.
#   - Pre-Production: every deliverable has moved past In Design (each
#     one's own label is Pre-Production or Handed to Production) — this is
#     the same raw project_status value ('approved') that used to read
#     "Client Approved"; only the label/colour changed, see the module
#     docstring for where that moment is still timestamped.
#   - Handed to Production: every deliverable itself reads Handed to
#     Production. This is also what the Projects list's Design Completed
#     tab shows (project_list.py) — there's no separate "Design Completed"
#     label anymore, Handed to Production IS what lands there.
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