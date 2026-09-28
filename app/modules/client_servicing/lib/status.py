"""
CS operational status: the CS lifecycle laid over the platform's derived status.
The platform models only design, approval and handoff, so CS sets later stages
(production, logistics, finance) by hand on its companion row. Never touches
Project.project_status.
"""
from app.modules.core.shared.lib.status_vocabulary import derive_project_status


# CS status dropdown, in lifecycle order. Briefing, In Production, On Hold and
# Cancelled can also be derived; the rest are set by hand only.
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

# label -> the app's status-pill colour modifier, grouped by lifecycle family.
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

# Platform-derived label -> CS display label. 'In Production' is display only;
# the project itself stays Handed to Production.
_AUTO_RELABEL = {
    'Briefed': 'Briefing',
    'Handed to Production': 'In Production',
}


def _modifier_for(label):
    return _MODIFIER_BY_LABEL.get(label, _DEFAULT_MODIFIER)


def effective_cs_status(project):
    """(label, css_modifier, is_auto) for a project's CS status cell. Manual
    cs_status wins when set; otherwise the derived status in CS wording."""
    cs = project.client_servicing
    if cs and cs.cs_status:
        return (cs.cs_status, _modifier_for(cs.cs_status), False)

    base_label = derive_project_status(project)[0]
    label = _AUTO_RELABEL.get(base_label, base_label)
    return (label, _modifier_for(label), True)


def cs_design_indicator(project):
    """Chip labels for an In-Design row's open design streams ([] if none).
    Standard briefs: 2D / 3D / Technical. C&CM: Concept & KV until concept
    approval, then Customer Artwork until every deliverable is approved."""
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
