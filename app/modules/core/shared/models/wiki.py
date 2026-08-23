from app.modules.core.shared.extensions import db
from datetime import datetime


class WikiSection(db.Model):
    """
    Top level Sections in the wiki (E.G Cs View, Designer View).
    relevant_roles is a comma-separated list of the roles this secton is for
    (drives the role indicator in the viewer). Empty = relevant to everyone.
    """

    __tablename__ = 'wiki_sections'

    id              = db.Column(db.Integer, primary_key=True)
    title           = db.Column(db.String(200), nullable=False)
    slug            = db.Column(db.String(200), nullable=False, unique=True)
    relevant_roles  = db.Column(db.String(200)) #e.g cs, admin or designer/team_lead
    sort_order      = db.Column(db.Integer, default=0)
    is_published    = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    articles = db.relationship(
        'WikiArticle',
        back_populates='section',
        cascade='all, delete-orphan',
        order_by='WikiArticle.sort_order'
    )

    def __repr__(self):
        return f'<Wiki Section {self.slug}>'


class WikiArticle(db.Model):
    """
    A single page within a wiki section. sections_json stores content as a JSON array of block objects
    same pattern as BlogPost, supporting: body, richtext, h3, callout,
    callout-pins, list, image, video block types.
    """

    __tablename__='wiki_articles'

    id              = db.Column(db.Integer, primary_key=True)
    section_id      = db.Column(db.Integer, db.ForeignKey('wiki_sections.id'), nullable=False)
    title           = db.Column(db.String(200), nullable=False)
    slug            = db.Column(db.String(200), nullable=False)
    sections_json    = db.Column(db.Text)
    sort_order      = db.Column(db.Integer, default=0)
    is_published    = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    section      = db.relationship('WikiSection', back_populates='articles')

    def __repr__(self):
        return f'<WikiArticle {self.slug} in section {self.section_id}>'


# ═══════════════════════════════════════════════════════════════════════
# Achievement system (gamification) — added 3 Jul 2026
# Six new tables, no changes to any existing table. Registered here so
# create_tables.py picks them up automatically (same as NotificationSound
# and RoleTitle above) — no separate migration script needed since none
# of this touches an existing table's columns.
# ═══════════════════════════════════════════════════════════════════════
