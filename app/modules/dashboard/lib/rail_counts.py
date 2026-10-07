"""The numbers on the dashboard rail: how many things on each page need the
person. Project counters read the loader, never their own project query; the
admin system badges read the system module's tables through its services."""
from app.modules.dashboard.lib.project_loader import request_memo
from app.modules.dashboard.lib.rails import rail_for
from app.modules.system.services import health

# Page key -> counter(user) -> int. A page without a counter has no badge;
# each section registers its counter here when its page is built.
COUNTERS = {
    'errors': lambda user: health.new_error_groups(),
    'jobs': lambda user: health.failed_jobs(),
}


def rail_counts(user):
    """{page key: count or None} for the pages on `user`'s rail, once per request; 0 becomes None so no badge shows."""
    rail = rail_for(user)

    def compute():
        return {key: COUNTERS[key](user) or None for key in rail.pages if key in COUNTERS}

    return request_memo(('rail_counts', rail.key, getattr(user, 'id', None)), compute)
