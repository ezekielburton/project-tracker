"""Adoption score: the average of a set of ratios, as a whole percent. A ratio
with nothing to count (0 of 0) is left out, not scored as zero."""

# Component key -> label shown on the PDF, in display order per report.
LABELS = {
    'complete': 'Projects with complete details',
    'deadlines': 'Deadlines with a logged delivery',
    'approvals': 'Approvals made in OVP',
    'uploaded': 'Deliverables uploaded in OVP',
    'active': 'Days active',
}


def percent(done, total):
    return round(100 * done / total) if total else None


def score(components):
    """components: [(key, done, total)]. Mean of the countable ratios, 0-100."""
    ratios = [done / total for _, done, total in components if total]
    return round(100 * sum(ratios) / len(ratios)) if ratios else 0


def pooled(component_lists):
    """Adds the people's ratios key by key, for a department's components."""
    sums = {}
    for components in component_lists:
        for key, done, total in components:
            d, t = sums.get(key, (0, 0))
            sums[key] = (d + done, t + total)
    return [(key, d, t) for key, (d, t) in sums.items()]
