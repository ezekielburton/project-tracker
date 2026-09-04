"""
CS operational status — the CS master-sheet lifecycle laid over the
platform's own derived status. The platform models only the
design -> approval -> handoff stages (status_vocabulary.derive_project_status);
production, procurement, logistics and finance stages aren't modelled yet,
so CS carries them as a manual overlay on its own companion row.

effective_cs_status() returns the manual cs_status when set (it always
wins, sticky until cleared), else the platform-derived status re-labelled
into CS vocabulary. Nothing here writes, and nothing touches
Project.project_status — the projects page, dashboard and DI board are
unaffected.
"""
from app.modules.core.shared.lib.status_vocabulary import derive_project_status


# The CS master-sheet status vocabulary, in lifecycle order. The dropdown
# offers all of these; the first handful also derive automatically, the
# rest are manual-only overlays (stages the platform doesn't model yet).
CS_STATUS_OPTIONS = [
    'Briefing',
    'Survey',
    'KV in Progress',
    'AW in Progress',
    '3D in Progress',
    'TD in Progress',
    'Pending Approval',
    'Pending Quotation',
    'Pending LPO',
    'Pending Production',
    'In Production',
    'Installed',
    'Prize Distribution',
    'ED Closure',
    'Pending Invoice',
    'Partial Invoicing',
    'Invoiced',
    'On Hold',
    'Cancelled',
]

# label -> pill colour modifier, reusing the app's existing status-pill
# modifiers, grouped by lifecycle family.
_MODIFIER_BY_LABEL = {
    'In Design': 'coral',
    'KV in Progress': 'coral',
    'AW in Progress': 'coral',
    '3D in Progress': 'coral',
    'TD in Progress': 'coral',
    'Briefing': 'sky',
    'Survey': 'sky',
    'Pending Approval': 'sage',
    'Pre-Production': 'oak',
    'Pending Quotation': 'oak',
    'Pending LPO': 'oak',
    'Pending Production': 'oak',
    'In Production': 'clover',
    'Installed': 'clover',
    'Prize Distribution': 'lavender',
    'ED Closure': 'lavender',
    'Pending Invoice': 'canary',
    'Partial Invoicing': 'canary',
    'Invoiced': 'canary',
    'On Hold': 'poppy',
    'Cancelled': 'salmon',
}
_DEFAULT_MODIFIER = 'coral'

# Platform-derived label -> CS display label. Only what derive_project_status
# actually emits is re-labelled; everything past handoff is manual-only.
# 'In Production' is a display alias — the underlying project stays
# Handed to Production.
_AUTO_RELABEL = {
    'Briefed': 'Briefing',
    'Handed to Production': 'In Production',
}


def _modifier_for(label):
    return _MODIFIER_BY_LABEL.get(label, _DEFAULT_MODIFIER)


def effective_cs_status(project):
    """(label, css_modifier, is_auto) for a project's CS status cell.

    Manual cs_status wins when set (is_auto False); otherwise the
    platform-derived status re-labelled into CS vocabulary (is_auto True).
    Never reads or writes Project.project_status beyond what
    derive_project_status already does."""
    cs = project.client_servicing
    if cs and cs.cs_status:
        return (cs.cs_status, _modifier_for(cs.cs_status), False)

    base_label = derive_project_status(project)[0]
    label = _AUTO_RELABEL.get(base_label, base_label)
    return (label, _modifier_for(label), True)


def cs_design_indicator(project):
    """Active design streams for an In-Design row, as short chip labels
    ([] when none). Standard briefs show the open 2D/3D/Technical streams;
    C&CM shows Concept & KV until concept approval, then Customer Artwork
    while artwork is still in progress."""
    if project.brief_type == 'ccm':
        if project.concept_approved_at is None:
            return ['Concept & KV']
        if any(d.status != 'approved' for d in project.project_deliverables):
            return ['Customer Artwork']
        return []

    deliverables = project.project_deliverables
    chips = []
    if any(d.needs_2d and d.status_2d != 'approved' for d in deliverables):
        chips.append('2D')
    if any(d.needs_3d and d.status_3d != 'approved' for d in deliverables):
        chips.append('3D')
    if any(d.needs_technical and d.technical_status != 'approved' for d in deliverables):
        chips.append('Technical')
    return chips
