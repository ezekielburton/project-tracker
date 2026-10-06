"""
What makes a CS job "missing data". One definition shared by the Dashboard's
strip and the Table's Missing-data chip, so the count and the rows agree.
"""

# Chip id the Table reads from ?chip=; the Table JS declares it in its contract.
MISSING_DATA_CHIP = 'missing_data'


def missing_fields(project):
    """Labels of the fields a job still needs; empty when complete. Every
    project must have a CS lead, so only these can be blank."""
    missing = []
    if project.installation_date is None:
        missing.append('install date')
    if project.value is None:
        missing.append('value')
    if not (project.job_number or '').strip():
        missing.append('job number')
    return missing
