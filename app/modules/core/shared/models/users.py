from app.modules.core.shared.extensions import db, login_manager
from app.modules.core.shared.lib.org import LEAD_SENIORITY, LEGACY_ROLES, legacy_role_for
from flask_login import UserMixin
from datetime import datetime
from sqlalchemy import and_, case
from sqlalchemy.ext.hybrid import hybrid_property


class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    # Org model: capabilities come from department + seniority; is_admin grants
    # everything. Keys are listed in core/shared/lib/org.py.
    department = db.Column(db.String(40), nullable=True)
    job_role_id = db.Column(db.Integer, db.ForeignKey('job_roles.id', ondelete='SET NULL'), nullable=True)
    seniority = db.Column(db.String(20), nullable=False, default='none')
    reports_to_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)

    job_role = db.relationship('JobRole')
    reports_to = db.relationship('User', remote_side=[id], foreign_keys=[reports_to_id])
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

    @hybrid_property
    def role(self):
        """The role key the org fields amount to, for code not yet on the org
        model. Setting it fills department, seniority and is_admin from the key."""
        return legacy_role_for(self.department, self.seniority, self.is_admin)

    @role.inplace.setter
    def _role_setter(self, value):
        if value not in LEGACY_ROLES:
            raise ValueError(f'Unknown role: {value!r}')
        self.department, self.seniority, self.is_admin = LEGACY_ROLES[value]

    @role.inplace.expression
    @classmethod
    def _role_expression(cls):
        return case(
            (cls.is_admin.is_(True), 'admin'),
            (cls.seniority == 'management', 'management'),
            (and_(cls.department == 'design', cls.seniority.in_(LEAD_SENIORITY)), 'team_lead'),
            (cls.department == 'design', 'designer'),
            (cls.department == 'client_servicing', 'cs'),
            else_=cls.department,
        )

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


class JobRole(db.Model):
    """A job title someone in a department can hold; admin edits the list.
    A NULL department is for titles outside any department, e.g. General Manager."""
    __tablename__ = 'job_roles'
    __table_args__ = (
        db.UniqueConstraint('department', 'title', name='uq_job_roles_department_title'),
    )

    id = db.Column(db.Integer, primary_key=True)
    department = db.Column(db.String(40), nullable=True)
    title = db.Column(db.String(100), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    # Hidden titles stay on the people who hold them but leave the picker.
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def __repr__(self):
        return f'<JobRole {self.department}: {self.title}>'


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
