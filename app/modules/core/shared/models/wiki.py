from app.modules.core.shared.extensions import db
from datetime import datetime
from sqlalchemy import Computed
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import deferred

# Title words outrank body words. The migration reads this too, so the two never differ.
SEARCH_VECTOR_SQL = (
    "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(search_text, '')), 'B')"
)


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
    created_by_id   = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    updated_by_id   = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    # Last time someone confirmed the article is still right. Every save counts.
    reviewed_at     = db.Column(db.DateTime)

    # The live document's plain words, set on save. Postgres builds search_vector
    # from them and the title. Deferred, so the reader and tray never load them.
    search_text     = deferred(db.Column(db.Text))
    search_vector   = deferred(db.Column(TSVECTOR, Computed(SEARCH_VECTOR_SQL, persisted=True)))

    __table_args__ = (
        db.Index('ix_wiki_articles_search_vector', 'search_vector', postgresql_using='gin'),
    )

    section      = db.relationship('WikiSection', back_populates='articles')
    created_by   = db.relationship('User', foreign_keys=[created_by_id])
    updated_by   = db.relationship('User', foreign_keys=[updated_by_id])

    def __repr__(self):
        return f'<WikiArticle {self.slug} in section {self.section_id}>'


class WikiSearchMiss(db.Model):
    """A search that found nothing. phrase_key holds its stemmed words, sorted,
    so different wordings of one question are counted together."""

    __tablename__ = 'wiki_search_misses'

    id           = db.Column(db.Integer, primary_key=True)
    phrase       = db.Column(db.String(200), nullable=False)
    phrase_key   = db.Column(db.Text, nullable=False, index=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    note         = db.Column(db.Text)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    dismissed_at = db.Column(db.DateTime)


class WikiArticleView(db.Model):
    """One person reading one article, counted at most once a day. source is
    'page' (the reader) or 'tray' (the Help tray)."""

    __tablename__ = 'wiki_article_views'
    __table_args__ = (
        db.Index('ix_wiki_article_views_article_viewed', 'article_id', 'viewed_at'),
    )

    id         = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('wiki_articles.id', ondelete='CASCADE'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    source     = db.Column(db.String(10), nullable=False)
    viewed_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class WikiArticleVote(db.Model):
    """One person's "Useful?" answer on one article; they can change it. A "no"
    may carry a note saying what was missing."""

    __tablename__ = 'wiki_article_votes'
    __table_args__ = (
        db.UniqueConstraint('article_id', 'user_id', name='uq_wiki_article_votes_article_user'),
    )

    id         = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('wiki_articles.id', ondelete='CASCADE'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    helpful    = db.Column(db.Boolean, nullable=False)
    note       = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
