from app.modules.core.shared.models import User


def active_users_query():
    """Base query for anything that offers a person to pick (dropdowns,
    filters, mentions): active accounts only."""
    return User.query.filter(User.is_active.is_(True))


def active_users(*roles):
    """Active users ordered by name, optionally narrowed to the given roles."""
    q = active_users_query()
    if roles:
        q = q.filter(User.role.in_(roles))
    return q.order_by(User.name).all()