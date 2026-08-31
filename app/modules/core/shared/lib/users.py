from app.modules.core.shared.models import User


def active_users_query():
    """Base query for user pickers — active accounts only.
    Deactivated users are kept in the DB but excluded from anything
    that offers a person to pick (dropdowns, filters, mentions)."""
    return User.query.filter(User.is_active.is_(True))


def active_users(*roles):
    """Active users, name-ordered. Pass one or more roles to narrow
    (e.g. active_users('designer', 'team_lead')); no roles = all active."""
    q = active_users_query()
    if roles:
        q = q.filter(User.role.in_(roles))
    return q.order_by(User.name).all()