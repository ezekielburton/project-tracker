from app.modules.core.shared.extensions import db
from datetime import datetime


#  ---- Wiki -------------------------------

class WikiSection(db.Model):
    """
    A top-level wiki section (e.g. CS View). relevant_roles is a comma-separated
    role list shown as role badges; empty means everyone.
    """

    __tablename__ = 'wiki_sections'

    id              = db.Column(db.Integer, primary_key=True)
    title           = db.Column(db.String(200), nullable=False)
    slug            = db.Column(db.String(200), nullable=False, unique=True)
    relevant_roles  = db.Column(db.String(200)) # e.g. "cs,admin"
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
    A wiki page. sections_json is the live Editor.js document and
    draft_sections_json the autosaved working copy; nothing reads
    legacy_sections_json. help_key names the app page this article explains
    (one article per key).
    """

    __tablename__='wiki_articles'

    id              = db.Column(db.Integer, primary_key=True)
    section_id      = db.Column(db.Integer, db.ForeignKey('wiki_sections.id'), nullable=False)
    title           = db.Column(db.String(200), nullable=False)
    slug            = db.Column(db.String(200), nullable=False)
    help_key        = db.Column(db.String(100))
    sections_json   = db.Column(db.Text)
    legacy_sections_json = db.Column(db.Text)
    draft_sections_json  = db.Column(db.Text)
    draft_saved_at       = db.Column(db.DateTime)
    sort_order      = db.Column(db.Integer, default=0)
    is_published    = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    section      = db.relationship('WikiSection', back_populates='articles')

    def __repr__(self):
        return f'<WikiArticle {self.slug} in section {self.section_id}>'
