"""
HSE labels to the shared status-pill colours.

The pill CSS owns shape and colour only — which colour a label gets is
decided here, the same split core/shared/lib/status_vocabulary.py uses for
project statuses.
"""

# Status -> status-pill modifier. Covers both the stored workflow statuses
# and the computed expiry ones.
STATUS_MODIFIERS = {
    'Open': 'sky',
    'In Progress': 'canary',
    'Escalated': 'poppy',
    'Resolved': 'clover',
    'Closed': 'clover',
    'Valid': 'clover',
    'Expiring soon': 'canary',
    'Expired': 'poppy',
    # Work that gets scheduled and completed.
    'Scheduled': 'sky',
    'Booked': 'sky',
    'Completed': 'clover',
    'Done': 'clover',
    'Cancelled': 'oak',
    'Overdue': 'poppy',
    # Requests.
    'Requested': 'sky',
    'Pending': 'sky',
    'Issued': 'clover',
    'Backordered': 'canary',
    'Rejected': 'oak',
    # Machine condition.
    'Working': 'clover',
    'Under Maintenance': 'canary',
    'Not Working': 'poppy',
    # Tools.
    'In Service': 'clover',
    'Under Repair': 'canary',
    'Retired': 'oak',
    'Decommissioned': 'oak',
}

# Severity -> modifier. Deliberately not the UI accent: coral means
# interactive everywhere else in the app.
SEVERITY_MODIFIERS = {
    'Low': 'sage',
    'Medium': 'oak',
    'High': 'canary',
    'Critical': 'poppy',
}


def status_modifier(label):
    return STATUS_MODIFIERS.get(label, 'oak')


def severity_modifier(label):
    return SEVERITY_MODIFIERS.get(label, 'oak')
