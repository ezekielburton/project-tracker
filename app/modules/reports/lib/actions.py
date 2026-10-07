"""Which activity-log actions count as real work. Opening a page, starting a
draft or asking for edit access doesn't. A new project action counts only
once it is listed here."""

WORK_ACTIONS = frozenset({
    # Projects and briefs
    'project_created', 'project_edited', 'project_cancelled',
    'customer_added', 'customer_cancelled', 'customer_reactivated',
    'cs_lead_reassigned', 'project_owner_assigned', 'secondary_cs_added', 'secondary_cs_removed',
    'brief_flag_created', 'brief_flag_reply', 'brief_flag_resolved',
    'note_added', 'site_visit_logged', 'file_uploaded',
    # Deliverables and design leads
    'deliverable_created', 'deliverable_updated', 'deliverable_assigned', 'deliverable_unassigned',
    'deliverable_deleted', 'deliverables_duplicated',
    'designer_assigned', 'lead_assigned', 'lead_transferred', 'lead_removed',
    # Submissions and reviews
    'submission_draft_file_added', 'submission_draft_file_removed', 'submission_draft_main_deck_changed',
    'internal_review_submitted', 'internal_revision_flagged', 'revision_requested',
    'submitted_to_client', 'project_approved', 'deliverables_approved',
    # Pre-Production
    'preprod_stream_marked_done', 'preprod_stream_approved', 'preprod_stream_flagged',
    'preprod_stream_assigned', 'preprod_skipped',
    # Client Servicing
    'client_servicing_edit', 'client_servicing_close',
})

# Approvals recorded in OVP: pre-production streams, and client approvals logged by CS.
APPROVAL_ACTIONS = frozenset({'preprod_stream_approved', 'project_approved', 'deliverables_approved'})

# One revision round each.
REVISION_ACTIONS = frozenset({'revision_requested', 'internal_revision_flagged'})

# A designer uploading a Pre-Production stream.
STREAM_UPLOAD_ACTION = 'preprod_stream_marked_done'

# Deliverable statuses that mean the designer handed the work in.
DELIVERED_STATUSES = ('internal_review', 'submitted_to_client', 'approved')
