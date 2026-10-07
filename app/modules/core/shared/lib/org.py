"""The org model: departments, seniority levels, the role-key bridge, and the
checks that pick a branch by where someone sits (is_designer() and friends).
These choose what a person sees, never whether they may; that is can()."""

# Department key -> label, in picker order. Stored in User.department.
DEPARTMENTS = {
    'client_servicing': 'Client Servicing',
    'project_owner': 'Project Owners',
    'design': 'Design',
    'production': 'Production',
    'logistics': 'Logistics',
    'finance': 'Finance',
    'hr': 'HR',
    'digital_innovation': 'Digital Innovation',
    'hse': 'HSE',
}

# Seniority key -> label, lowest first. Stored in User.seniority.
SENIORITY_LEVELS = {
    'none': 'None',
    'manager': 'Manager',
    'head': 'Head of Department',
    'management': 'Management',
}

# Role key -> (department, seniority, is_admin). Lets code and tests that still
# speak in role keys read and write the org fields.
LEGACY_ROLES = {
    'admin': (None, 'none', True),
    'management': (None, 'management', False),
    'cs': ('client_servicing', 'none', False),
    'project_owner': ('project_owner', 'none', False),
    'designer': ('design', 'none', False),
    'team_lead': ('design', 'manager', False),
    'finance': ('finance', 'none', False),
    'digital_innovation': ('digital_innovation', 'none', False),
    'hr': ('hr', 'none', False),
    'production': ('production', 'none', False),
    'logistics': ('logistics', 'none', False),
    'hse': ('hse', 'none', False),
}

# Seniority levels that make someone in Design a lead.
LEAD_SENIORITY = ('manager', 'head')


def legacy_role_for(department, seniority, is_admin):
    """The role key these org fields amount to; None when they amount to none."""
    if is_admin:
        return 'admin'
    if seniority == 'management':
        return 'management'
    if department == 'design':
        return 'team_lead' if seniority in LEAD_SENIORITY else 'designer'
    if department == 'client_servicing':
        return 'cs'
    return department


def is_management(user):
    """True for someone with Management seniority, whatever their department."""
    return getattr(user, 'seniority', None) == 'management'


def is_admin(user):
    """True for an admin account."""
    return bool(getattr(user, 'is_admin', False))


def is_leadership(user):
    """Admin or Management: the people who take the company-wide branches."""
    return is_admin(user) or is_management(user)


def _works_in(user, department):
    """In `department` and not leadership; leadership takes the company-wide
    branches instead of a department's."""
    return not is_leadership(user) and getattr(user, 'department', None) == department


def is_cs(user):
    """Works in Client Servicing."""
    return _works_in(user, 'client_servicing')


def is_project_owner(user):
    """Works as a Project Owner."""
    return _works_in(user, 'project_owner')


def is_designer(user):
    """Does design work: a designer or a design lead."""
    return _works_in(user, 'design')


def is_design_lead(user):
    """A designer at Manager or Head seniority; leads manage their team's assignments."""
    return is_designer(user) and getattr(user, 'seniority', None) in LEAD_SENIORITY


def is_plain_designer(user):
    """A designer below lead seniority; they can only assign themselves."""
    return is_designer(user) and not is_design_lead(user)


def is_department_head(user):
    """Head of Department seniority, outside leadership."""
    return not is_leadership(user) and getattr(user, 'seniority', None) == 'head'


def department_label(user):
    """The label of `user`'s department; "Management" for Management seniority
    with no department; None otherwise."""
    department = getattr(user, 'department', None)
    if department in DEPARTMENTS:
        return DEPARTMENTS[department]
    if is_management(user):
        return SENIORITY_LEVELS['management']
    return None


def seniority_label(user):
    """The label of `user`'s seniority; None when they have none."""
    seniority = getattr(user, 'seniority', None)
    if seniority in (None, 'none'):
        return None
    return SENIORITY_LEVELS.get(seniority)
