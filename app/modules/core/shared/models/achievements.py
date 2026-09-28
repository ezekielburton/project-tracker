from app.modules.core.shared.extensions import db


# ═══════════════════════════════════════════════════════════════════════
# Achievement system (gamification).
# ═══════════════════════════════════════════════════════════════════════

class AchievementCategory(db.Model):
    """Display grouping for achievements (e.g. "Submissions"). No effect on
    earning."""
    __tablename__ = 'achievement_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(50), nullable=True)        # emoji or icon reference
    display_order = db.Column(db.Integer, default=0)       # sort order in the admin panel and profile page

    def __repr__(self):
        return f'<AchievementCategory {self.name}>'


class AchievementBorder(db.Model):
    """A profile-banner border. Stores only a class name; the styling lives in
    achievements.css, so a new border needs the CSS class first."""
    __tablename__ = 'achievement_borders'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)       # admin-facing label, e.g. "Golden Shimmer"
    css_class = db.Column(db.String(100), nullable=False)  # e.g. "border-golden-shimmer" — must exist in achievements.css

    def __repr__(self):
        return f'<AchievementBorder {self.name}>'


class Achievement(db.Model):
    """
    An achievement that can be earned (who earned it is UserAchievement).
    trigger_event is free text matched against check_achievements()'s
    event_type (services/achievements.py); a typo means it never fires.
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
    One user's progress toward one achievement, created by
    check_achievements(). earned_at is stamped once, when progress reaches
    the threshold.
    """
    __tablename__ = 'user_achievements'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    achievement_id = db.Column(db.Integer, db.ForeignKey('achievements.id'), nullable=False)
    progress = db.Column(db.Integer, default=0)
    earned_at = db.Column(db.DateTime, nullable=True)

    # One progress row per user per achievement; guards the upsert against races.
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
    A user's chosen badge, title and border (one row per user). The table does
    not check these were earned; the settings UI only offers earned items.
    """
    __tablename__ = 'user_display_settings'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)

    # Badge and title point at UserAchievement, so they refer to an earned instance.
    active_badge_id = db.Column(db.Integer, db.ForeignKey('user_achievements.id'), nullable=True)
    active_title_id = db.Column(db.Integer, db.ForeignKey('user_achievements.id'), nullable=True)
    active_border_id = db.Column(db.Integer, db.ForeignKey('achievement_borders.id'), nullable=True)

    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<UserDisplaySettings user={self.user_id}>'


class UserPinnedAchievement(db.Model):
    """Up to 5 achievements featured on a user's profile card, one row per slot."""
    __tablename__ = 'user_pinned_achievements'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user_achievement_id = db.Column(db.Integer, db.ForeignKey('user_achievements.id'), nullable=False)
    pin_order = db.Column(db.Integer, nullable=False)   # 1-5, left to right

    # One achievement per slot. Saving replaces the whole set (delete, then
    # re-insert), so slot swaps never collide.
    __table_args__ = (
        db.UniqueConstraint('user_id', 'pin_order', name='uq_user_pin_order'),
    )

    user = db.relationship('User', foreign_keys=[user_id])
    user_achievement = db.relationship('UserAchievement', foreign_keys=[user_achievement_id])

    def __repr__(self):
        return f'<UserPinnedAchievement user={self.user_id} slot={self.pin_order}>'
