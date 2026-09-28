from datetime import datetime

from app.modules.core.shared.extensions import db


class OvpChampion(db.Model):
    """That week's OVP champion for one department. Each week is a new row, so
    history is kept."""
    __tablename__ = 'ovp_champions'
    __table_args__ = (
        db.UniqueConstraint('week_start', 'department', name='uq_ovp_champions_week_department'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # One of CHAMPION_DEPARTMENTS in core/shared/lib/champions.
    department = db.Column(db.String(50), nullable=False)
    # The Monday of the week this assignment covers.
    week_start = db.Column(db.Date, nullable=False)
    set_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])
    set_by = db.relationship('User', foreign_keys=[set_by_id])

    def __repr__(self):
        return f'<OvpChampion {self.department} user {self.user_id} week {self.week_start}>'
