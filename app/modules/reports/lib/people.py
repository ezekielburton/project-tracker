"""Who each department report covers: active people in that department.
Leadership (admin, Management) is left out by the org helpers."""
from app.modules.core.shared.lib.org import is_cs, is_design_lead, is_designer, is_project_owner
from app.modules.core.shared.models import User

# Department report keys; each matches its User.department key.
DEPARTMENT_REPORTS = ('client_servicing', 'project_owner', 'design')

_BELONGS = {
    'client_servicing': is_cs,
    'project_owner': is_project_owner,
    'design': is_designer,
}


def people_for(report):
    """Active people the report covers, by name."""
    users = (User.query.filter(User.is_active.is_(True), User.department == report)
             .order_by(User.name).all())
    return [u for u in users if _BELONGS[report](u)]


def everyone():
    """{report: [users]} for every department report."""
    return {report: people_for(report) for report in DEPARTMENT_REPORTS}


def is_lead(user):
    return is_design_lead(user)
