"""
Maps HSE status and severity labels to shared status-pill colour modifiers
(same split as core/shared/lib/status_vocabulary.py).
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
    'Lost': 'poppy',
}

# Statuses that count as open. The rail badges, Overview and My performance
# all use this set. Kept out of query.py so metric code can import it
# without the models.
OPEN_STATUSES = ('Open', 'In Progress', 'Escalated')

# The registers an inspection is logged in.
INSPECTION_REGISTERS = ('general_inspection', 'vehicle_inspection', 'forklift_inspection')

# Computed expiry statuses that count as needing attention.
OPEN_EXPIRY_STATUSES = ('Expiring soon', 'Expired')

# Severity -> modifier. Avoids coral, which means "interactive" in the app.
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
