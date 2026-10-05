"""Whether a wiki article has been reviewed recently, by calendar quarter."""
from datetime import datetime


def _quarter(moment):
    return moment.year, (moment.month - 1) // 3


def reviewed_this_quarter(reviewed_at, now=None):
    """True when the last review falls in the current calendar quarter."""
    return bool(reviewed_at) and _quarter(reviewed_at) == _quarter(now or datetime.utcnow())


def review_label(reviewed_at, now=None):
    """'Reviewed this quarter', 'Reviewed Jun 2026', or '' when never reviewed."""
    if not reviewed_at:
        return ''
    if reviewed_this_quarter(reviewed_at, now):
        return 'Reviewed this quarter'
    return 'Reviewed ' + reviewed_at.strftime('%b %Y')
