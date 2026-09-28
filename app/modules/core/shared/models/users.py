from app.modules.core.shared.extensions import db, login_manager
from flask_login import UserMixin
from datetime import datetime


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
    # False = deactivated: hidden from user pickers and blocked from login. The
    # row stays so existing references still resolve.
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    nas_url = db.Column(db.String(500), nullable=True)

    # JSON string of per-type email opt-outs, e.g. '{"flag_reply": false}'.
    # A missing key means enabled.
    notification_prefs = db.Column(db.String(2000), nullable=True)

    # Profile page fields
    bio = db.Column(db.Text, nullable=True)
    avatar_filename = db.Column(db.String(255), nullable=True)   # app/static/avatars/<filename>
    banner_filename = db.Column(db.String(255), nullable=True)   # app/static/banners/<filename>
    favorite_food = db.Column(db.String(100), nullable=True)
    birthday = db.Column(db.Date, nullable=True)

    # First-time setup
    wizard_completed = db.Column(db.Boolean, default=False, nullable=False)
    avatar_step_completed = db.Column(db.Boolean, nullable=False, default=False)

    # 'light' or 'dark'. NULL = no saved choice; the client falls back to
    # localStorage, then light.
    theme_preference = db.Column(db.String(10), nullable=True)
    # Last Signal tray open; the launcher badge counts newer bug, feature and
    # friction items.
    signal_seen_at = db.Column(db.DateTime, nullable=True)

    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        """Session token "<id>:<password fingerprint>". Changing the password
        invalidates every existing session."""
        return f"{self.id}:{self.password_hash[-12:]}"

    def wants_notification(self, key):
        """True if this user wants email for `key`; True when unset or unparseable.
        """
        import json
        if not self.notification_prefs:
            return True
        try:
            prefs = json.loads(self.notification_prefs)
            return prefs.get(key, True)
        except (ValueError, TypeError):
            return True

    def __repr__(self):
        return f'<User {self.email}>'


@login_manager.user_loader
def load_user(token):
    """
    Load a user from a "{user_id}:{fingerprint}" token (fingerprint = last 12
    chars of the password hash). A stale fingerprint returns None, logging out.
    """
    parts = token.split(':', 1)
    try:
        user_id = int(parts[0])
    except (ValueError, IndexError):
        return None
    user = User.query.get(user_id)
    # A deactivated account loads as anonymous, so an existing (remember-me)
    # session never carries it as current_user.
    if user is None or not user.is_active:
        return None
    if len(parts) == 2 and parts[1] != user.password_hash[-12:]:
        return None
    return user


class RoleTitle(db.Model):
    """
    Admin-editable fun title per role on the profile page (e.g. cs -> "Client
    Shepherd"). Falls back to DEFAULT_ROLE_TITLES.
    """
    __tablename__ = 'role_titles'

    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(50), nullable=False, unique=True)
    title = db.Column(db.String(100), nullable=False)

    def __repr__(self):
        return f'<RoleTitle {self.role}: {self.title}>'


# Fallback role titles when a role has no RoleTitle row.
DEFAULT_ROLE_TITLES = {
    'admin': 'System Overlord',
    'cs': 'Client Shepherd',
    'designer': 'Pixel Architect',
    'team_lead': 'Design Captain',
    'management': 'The Big Picture',
    'project_owner': 'Project Keeper',
    'finance': 'The Ledger',
    'digital_innovation': 'Systems Tinkerer',
    'hr': 'Culture Keeper',
    'production': 'The Fabricator',
    'logistics': 'Route Master',
}


class UserTableLayout(db.Model):
    """
    One user's column order and widths for one table, auto-saved as they drag.
    `layout` is a JSON array of {'key', 'width' (px)} in display order.
    table_key looks like 'project_list:my'.
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


class ProjectTableView(db.Model):
    """A user's saved Projects view: a name, the preset it builds on, and its
    saved filters and sort."""
    __tablename__ = 'project_table_views'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    base_view = db.Column(db.String(20), nullable=False) # my / all / design_complete
    filters = db.Column(db.JSON, nullable=True) 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='project_table_views')
