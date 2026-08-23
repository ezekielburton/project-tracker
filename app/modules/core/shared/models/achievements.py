from app.modules.core.shared.extensions import db
from datetime import datetime


# ═══════════════════════════════════════════════════════════════════════
# Achievement system (gamification). These tables are registered here so
# create_tables.py picks them up automatically.
# ═══════════════════════════════════════════════════════════════════════

class AchievementCategory(db.Model):
    """
    Groups related achievements together for display (e.g. "Submissions",
    "Quality", "Community"). Purely organizational — has no effect on
    whether an achievement can be earned.
    """
    __tablename__ = 'achievement_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(50), nullable=True)        # emoji or icon reference shown next to the category name
    display_order = db.Column(db.Integer, default=0)       # controls sort order in the admin panel + profile page

    def __repr__(self):
        return f'<AchievementCategory {self.name}>'


class AchievementBorder(db.Model):
    """
    A selectable decorative border style for the profile banner. css_class
    must match a real class defined in achievements.css — this table only
    stores the *name* of that class, not any actual styling, so adding a
    new border is: write the CSS class, then register it here via the
    admin panel.
    """
    __tablename__ = 'achievement_borders'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)       # admin-facing label, e.g. "Golden Shimmer"
    css_class = db.Column(db.String(100), nullable=False)  # e.g. "border-golden-shimmer" — must exist in achievements.css

    def __repr__(self):
        return f'<AchievementBorder {self.name}>'


class Achievement(db.Model):
    """
    The catalogue of achievements admins define — this table describes
    what CAN be earned, not who has earned it (see UserAchievement below
    for that). trigger_event is a free-text string matched against the
    event_type argument passed into check_achievements() in
    app/achievements.py — e.g. 'project_submitted', 'user_login'. There is
    intentionally no foreign key or enum constraining trigger_event: new
    event types can be wired up in code without a schema change, at the
    cost of a typo here silently meaning "this achievement never fires."
    """
    __tablename__ = 'achievements'

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('achievement_categories.id'), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    trigger_event = db.Column(db.String(100), nullable=False)
    threshold = db.Column(db.Integer, nullable=False, default=1)   # progress needed to earn (e.g. 10 submissions)
    is_hidden = db.Column(db.Boolean, default=False)               # shows as "???" until earned, see profile card
    badge_image = db.Column(db.String(255), nullable=True)         # filename in app/static/achievements/
    badge_type = db.Column(db.String(20), default='static')        # 'static' (<img>) or 'animated' (CSS class)
    reward_title = db.Column(db.String(100), nullable=True)        # optional fun title unlocked alongside the badge
    title_animated = db.Column(db.Boolean, default=False)
    border_id = db.Column(db.Integer, db.ForeignKey('achievement_borders.id'), nullable=True)
    display_order = db.Column(db.Integer, default=0)

    # foreign_keys spelled out explicitly on both relationships so
    # SQLAlchemy doesn't have to guess which FK each one refers to.
    category = db.relationship('AchievementCategory', foreign_keys=[category_id])
    border = db.relationship('AchievementBorder', foreign_keys=[border_id])

    def __repr__(self):
        return f'<Achievement {self.name} ({self.trigger_event} >= {self.threshold})>'


class UserAchievement(db.Model):
    """
    Tracks one user's progress toward one achievement. A row is created
    the first time check_achievements() sees a matching event for a user
    who doesn't have one yet (progress starts at 0 or 1 depending on how
    that call is made — see app/achievements.py for the exact upsert
    logic). earned_at stays NULL until progress >= the achievement's
    threshold, at which point it's stamped once and never changed again.
    """
    __tablename__ = 'user_achievements'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    achievement_id = db.Column(db.Integer, db.ForeignKey('achievements.id'), nullable=False)
    progress = db.Column(db.Integer, default=0)
    earned_at = db.Column(db.DateTime, nullable=True)

    # A user can only have ONE progress row per achievement — without this,
    # a race condition in the upsert logic could create duplicate rows that
    # each partially track progress, undercounting the real total.
    __table_args__ = (
        db.UniqueConstraint('user_id', 'achievement_id', name='uq_user_achievement'),
    )

    user = db.relationship('User', foreign_keys=[user_id])
    achievement = db.relationship('Achievement', foreign_keys=[achievement_id])

    def __repr__(self):
        earned = 'earned' if self.earned_at else f'{self.progress} progress'
        return f'<UserAchievement user={self.user_id} achievement={self.achievement_id} ({earned})>'


class UserDisplaySettings(db.Model):
    """
    One row per user (enforced via unique=True on user_id, not a composite
    key — there's only ever one "current" set of display choices, unlike
    UserPinnedAchievement below which is deliberately one-row-per-slot).
    Each of the three fields points at something the user has actually
    earned; the admin panel / settings page is responsible for
    only ever offering earned items as choices, but this table itself
    does not enforce that.
    """
    __tablename__ = 'user_display_settings'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)

    # Points at a UserAchievement (not an Achievement directly) — this is
    # deliberate: it ties the active badge/title to a *specific earned
    # instance*, so if the underlying Achievement were ever deleted by an
    # admin, the FK naturally has nothing valid to point at, rather than
    # silently displaying a badge/title the user never actually earned.
    active_badge_id = db.Column(db.Integer, db.ForeignKey('user_achievements.id'), nullable=True)
    active_title_id = db.Column(db.Integer, db.ForeignKey('user_achievements.id'), nullable=True)
    active_border_id = db.Column(db.Integer, db.ForeignKey('achievement_borders.id'), nullable=True)

    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<UserDisplaySettings user={self.user_id}>'


class UserPinnedAchievement(db.Model):
    """
    Up to 5 achievements a user has chosen to feature at the top of their
    profile card. One row per pinned slot, rather than a
    single row with 5 columns — this makes "drag to reorder" a matter of
    updating pin_order values, and "unpin one" a single DELETE, instead of
    shuffling values between fixed columns.
    """
    __tablename__ = 'user_pinned_achievements'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user_achievement_id = db.Column(db.Integer, db.ForeignKey('user_achievements.id'), nullable=False)
    pin_order = db.Column(db.Integer, nullable=False)   # 1-5, controls left-to-right display order

    # A user can't pin two different achievements into the same slot —
    # this is what makes "drag to reorder" safe to implement as a delete
    # and re-insert rather than needing careful in-place slot-swapping logic.
    __table_args__ = (
        db.UniqueConstraint('user_id', 'pin_order', name='uq_user_pin_order'),
    )

    user = db.relationship('User', foreign_keys=[user_id])
    user_achievement = db.relationship('UserAchievement', foreign_keys=[user_achievement_id])

    def __repr__(self):
        return f'<UserPinnedAchievement user={self.user_id} slot={self.pin_order}>'
