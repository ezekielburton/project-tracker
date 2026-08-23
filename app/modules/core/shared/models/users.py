from app.modules.core.shared.extensions import db, login_manager
from flask_login import UserMixin
from datetime import datetime


@login_manager.user_loader
def load_user(token):
    """
    Token format: "{user_id}:{password_fingerprint}"
    The fingerprint is the last 12 chars of the password hash.
    If the password changes, the fingerprint changes, killing all active sessions.
    """
    parts = token.split(':', 1)
    try:
        user_id = int(parts[0])
    except (ValueError, IndexError):
        return None
    user = User.query.get(user_id)
    if user is None:
        return None
    # Validate fingerprint — returns None (forces logout) if password was changed
    if len(parts) == 2 and parts[1] != user.password_hash[-12:]:
        return None
    return user

# User Class


class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='designer')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_conditional_reviewer = db.Column(db.Boolean, default=False)
    team = db.Column(db.String(20), nullable=True)
    nas_url = db.Column(db.String(500), nullable=True)

    # JSON string storing per-type email notification opt-outs.
    # Format: '{"new_project": false, "revision_flag": true}'
    # Missing key = enabled (default on, so existing users get everything).
    notification_prefs = db.Column(db.String(2000), nullable=True)

    # Profile page fields (added for the profile redesign)
    bio = db.Column(db.Text, nullable=True)
    avatar_filename = db.Column(db.String(255), nullable=True)   # app/static/avatars/<filename>
    banner_filename = db.Column(db.String(255), nullable=True)   # app/static/banners/<filename>
    favorite_food = db.Column(db.String(100), nullable=True)
    birthday = db.Column(db.Date, nullable=True)

    # First time setup columns
    wizard_completed = db.Column(db.Boolean, default=False, nullable=False)
    avatar_step_completed = db.Column(db.Boolean, nullable=False, default=False)

    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        """Return a token that includes a password fingerprint.
        Flask-Login stores this in the session/cookie. Changing the password
        changes the fingerprint, which invalidates all existing sessions."""
        return f"{self.id}:{self.password_hash[-12:]}"

    def wants_notification(self, key):
        """Return True if this user wants to receive email for the given pref key.
        Defaults to True when no prefs are saved or the key is absent — so all
        existing users continue to receive every notification after the migration.
        """
        import json
        if not self.notification_prefs:
            return True
        try:
            prefs = json.loads(self.notification_prefs)
            return prefs.get(key, True)  # unknown key → enabled by default
        except (ValueError, TypeError):
            return True

    def __repr__(self):
        return f'<User {self.email}>'

# Notification Class


class RoleTitle(db.Model):
    """
    Admin-editable "fun title" shown per role on the profile page
    (e.g. cs -> "Client Shepherd"). If a role has no row here yet,
    DEFAULT_ROLE_TITLES below is used instead — so the feature works
    out of the box before any admin edits it.
    """
    __tablename__ = 'role_titles'

    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(50), nullable=False, unique=True)
    title = db.Column(db.String(100), nullable=False)

    def __repr__(self):
        return f'<RoleTitle {self.role}: {self.title}>'


class UserTableLayout(db.Model):
    """
    One user's personal column widths + order for one table/view combination
    (e.g. the Projects page's 'my' tab). Silent, ambient preference — auto-saved
    as the user drags, never shared with other users, no explicit save action
    needed from them.

    `layout` is a JSON array of {'key': <column-key>, 'width': <px>} objects,
    in display order — the array's order IS the column order, and each
    entry's width is that column's current width. One row per (user, table_key)
    pair; table_key looks like 'project_list:my', 'project_list:all', etc.,
    so this same table can be reused by other pages later without needing a
    new table per page.
    """
    __tablename__ = 'user_table_layouts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    table_key = db.Column(db.String(100), nullable=False)
    layout = db.Column(db.JSON, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref='table_layouts')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'table_key', name='uq_user_table_layout'),
    )

    def __repr__(self):
        return f'<UserTableLayout user={self.user_id} table_key={self.table_key}>'


# Fallback titles — used whenever no RoleTitle row exists yet for a given role.
# Keeps the feature working immediately after this deploy, before any admin
# has visited the new "Role Titles" admin panel section to override them.


DEFAULT_ROLE_TITLES = {
    'admin': 'System Overlord',
    'cs': 'Client Shepherd',
    'designer': 'Pixel Architect',
    'team_lead': 'Design Captain',
    'management': 'The Big Picture',
}


class ProjectTableView(db.Model):
    """ A user's saved custom view on the Projects page. This consists of a name plus a remembered filter selectin,
    which is layered on top of the three fixed presets. Also saves sorting options"""
    __tablename__ = 'project_table_views'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    base_view = db.Column(db.String(20), nullable=False) # my / all / design_complete (renamed from 'approved' 18 Aug 2026 — see migrations/_backfill_project_table_view_base_view.py)
    filters = db.Column(db.JSON, nullable=True) 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='project_table_views')
