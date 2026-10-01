"""
Each user's Accounts view: the last Group by and the groups they have open in
each. Kept in UserTableLayout under STATE_KEY, so it follows them across
devices. Groups start collapsed; only open ones are stored.
"""
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import UserTableLayout
from app.modules.client_servicing.lib.accounts import GROUPS

STATE_KEY = 'client_servicing:accounts'
_MAX_KEYS = 500


def _keys(value):
    """Group keys as short strings; anything else is dropped."""
    if not isinstance(value, list):
        return []
    keys = {str(v) for v in value if isinstance(v, (str, int)) and not isinstance(v, bool)}
    return sorted(k for k in keys if 0 < len(k) <= 20)[:_MAX_KEYS]


def clean_state(raw):
    """A well-formed state from whatever was stored; bad parts fall back to the defaults."""
    raw = raw if isinstance(raw, dict) else {}
    opened = raw.get('open') if isinstance(raw.get('open'), dict) else {}
    return {
        'group': raw.get('group') if raw.get('group') in GROUPS else GROUPS[0],
        'open': {g: _keys(opened.get(g)) for g in GROUPS},
    }


def is_valid(data):
    """What the save endpoint accepts: a known group and an `open` map of lists."""
    return (isinstance(data, dict)
            and data.get('group') in GROUPS
            and isinstance(data.get('open'), dict)
            and all(isinstance(v, list) for v in data['open'].values()))


def load_state(user):
    row = UserTableLayout.query.filter_by(user_id=user.id, table_key=STATE_KEY).first()
    return clean_state(row.layout if row else None)


def save_state(user, raw):
    state = clean_state(raw)
    row = UserTableLayout.query.filter_by(user_id=user.id, table_key=STATE_KEY).first()
    if row:
        row.layout = state
    else:
        db.session.add(UserTableLayout(user_id=user.id, table_key=STATE_KEY, layout=state))
    db.session.commit()
    return state
