"""Account rules for the admin panel: the org fields an admin may set on a
person, checked server-side, and the JSON shape the panel reads."""
from app.modules.core.shared.extensions import db
from app.modules.core.shared.lib.org import DEPARTMENTS, SENIORITY_LEVELS
from app.modules.core.shared.models import JobRole, User

DESIGN_TEAMS = ('2D', '3D', 'Technical')
TITLE_MAX = 100


class AccountError(ValueError):
    """A save the panel must refuse; the message is shown to the admin."""


def org_options():
    """What the account forms pick from: departments, seniority levels, active
    job titles per department ('' = no department) and the design teams."""
    titles = {}
    for row in JobRole.query.filter_by(is_active=True).order_by(JobRole.sort_order, JobRole.title):
        titles.setdefault(row.department or '', []).append(row.title)
    return {
        'departments': [{'key': k, 'label': v} for k, v in DEPARTMENTS.items()],
        'seniority': [{'key': k, 'label': v} for k, v in SENIORITY_LEVELS.items()],
        'titles': titles,
        'teams': list(DESIGN_TEAMS),
    }


def user_json(user):
    """One account as the panel shows it."""
    return {
        'id': user.id, 'name': user.name, 'email': user.email,
        'role': user.role, 'team': user.team, 'is_active': user.is_active,
        'avatar_filename': user.avatar_filename,
        'department': user.department or '',
        'department_label': DEPARTMENTS.get(user.department, ''),
        'seniority': user.seniority,
        'seniority_label': SENIORITY_LEVELS.get(user.seniority, ''),
        'job_title': user.job_role.title if user.job_role else '',
        'reports_to_id': user.reports_to_id,
        'reports_to_name': user.reports_to.name if user.reports_to else '',
        'is_admin': bool(user.is_admin),
    }


def apply_org_fields(user, data, actor):
    """Set department, job title, seniority, Reports to, team and admin on `user`.
    Fields missing from `data` keep their current value. Raises AccountError on
    anything invalid; returns the changes as 'field: old → new' lines."""
    data = {**_current(user), **data}

    department = (data.get('department') or '').strip() or None
    if department is not None and department not in DEPARTMENTS:
        raise AccountError('Unknown department')

    seniority = (data.get('seniority') or 'none').strip()
    if seniority not in SENIORITY_LEVELS:
        raise AccountError('Unknown seniority')

    is_admin = bool(data.get('is_admin'))
    if user.id is not None and user.id == actor.id and not is_admin:
        raise AccountError('You cannot remove your own admin access')

    team = (data.get('team') or '').strip() or None
    if department != 'design':
        team = None
    elif team is not None and team not in DESIGN_TEAMS:
        raise AccountError('Unknown team')

    manager = _manager(user, data.get('reports_to_id'))
    job_role = _job_role(department, data.get('job_title'))

    before = _snapshot(user)
    user.department, user.seniority, user.is_admin, user.team = department, seniority, is_admin, team
    user.reports_to, user.job_role = manager, job_role
    after = _snapshot(user)
    return [f'{field}: {before[field] or "—"} → {after[field] or "—"}'
            for field in after if before[field] != after[field]]


def job_titles_json():
    """Every job title for the panel, hidden ones included, with how many people hold it."""
    counts = dict(db.session.query(User.job_role_id, db.func.count(User.id))
                  .filter(User.job_role_id.isnot(None)).group_by(User.job_role_id).all())
    rows = JobRole.query.order_by(JobRole.department, JobRole.sort_order, JobRole.title).all()
    return [{'id': r.id, 'title': r.title, 'department': r.department or '',
             'department_label': DEPARTMENTS.get(r.department, 'No department'),
             'is_active': r.is_active, 'people': counts.get(r.id, 0)} for r in rows]


def update_job_title(row, data):
    """Rename a job title and/or hide or show it. A rename onto another title in
    the same department is refused rather than merged."""
    if 'title' in data:
        title = _clean_title(data.get('title'))
        if not title:
            raise AccountError('Title is required')
        clash = (JobRole.query.filter_by(department=row.department)
                 .filter(db.func.lower(JobRole.title) == title.lower(), JobRole.id != row.id).first())
        if clash:
            raise AccountError('That title already exists in this department')
        row.title = title
    if 'is_active' in data:
        row.is_active = bool(data['is_active'])


def _current(user):
    return {
        'department': user.department or '', 'seniority': user.seniority or 'none',
        'is_admin': bool(user.is_admin), 'team': user.team or '',
        'reports_to_id': user.reports_to_id,
        'job_title': user.job_role.title if user.job_role else '',
    }


def _snapshot(user):
    return {
        'department': DEPARTMENTS.get(user.department, ''),
        'title': user.job_role.title if user.job_role else '',
        'seniority': SENIORITY_LEVELS.get(user.seniority, ''),
        'reports to': user.reports_to.name if user.reports_to else '',
        'team': user.team or '',
        'admin': 'yes' if user.is_admin else 'no',
    }


def _clean_title(raw):
    title = ' '.join((raw or '').split())
    if len(title) > TITLE_MAX:
        raise AccountError('Job title is too long')
    return title


def _manager(user, raw_id):
    """The Reports-to person, or None. Refuses the person themselves, a
    deactivated account they don't already report to, and anyone who already
    reports up to `user` (a loop would break the approval chain)."""
    if raw_id in (None, ''):
        return None
    try:
        manager = db.session.get(User, int(raw_id))
    except (TypeError, ValueError):
        raise AccountError('Unknown Reports to') from None
    if manager is None or (not manager.is_active and manager.id != user.reports_to_id):
        raise AccountError('Unknown Reports to')
    if user.id is not None:
        seen, current = set(), manager
        while current is not None and current.id not in seen:
            if current.id == user.id:
                raise AccountError(f'{manager.name} already reports up to {user.name}')
            seen.add(current.id)
            current = current.reports_to
    return manager


def _job_role(department, raw_title):
    """The job title row for `raw_title` in `department`, added to that
    department's list when new and shown again if hidden. Blank means none."""
    title = _clean_title(raw_title)
    if not title:
        return None
    row = (JobRole.query.filter_by(department=department)
           .filter(db.func.lower(JobRole.title) == title.lower()).first())
    if row is None:
        row = JobRole(department=department, title=title)
        db.session.add(row)
    elif not row.is_active:
        row.is_active = True
    return row
