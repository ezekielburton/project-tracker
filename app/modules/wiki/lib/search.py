"""Full-text search over wiki articles, using Postgres's built-in text search."""
import html
from collections import namedtuple

from markupsafe import Markup
from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import REGCONFIG

from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import WikiArticle, WikiSection

MAX_RESULTS = 50

# ts_headline wraps each match in these. document_text strips control characters,
# so they never occur in article text; they become <mark> after escaping.
MARK_START, MARK_STOP = '\x02', '\x03'
_HEADLINE_OPTIONS = (f'StartSel="{MARK_START}", StopSel="{MARK_STOP}", '
                     'MaxWords=35, MinWords=15, MaxFragments=2, FragmentDelimiter=" … "')

SearchHit = namedtuple('SearchHit', 'article section snippet')


def highlight_snippet(raw):
    """Escape the snippet first, then turn the match markers into <mark> tags."""
    safe = html.escape(raw or '', quote=False)
    return Markup(safe.replace(MARK_START, '<mark>').replace(MARK_STOP, '</mark>'))


def search_articles(text, include_drafts=False, limit=MAX_RESULTS):
    """Articles matching the words in text, best match first, each with a highlighted
    snippet. Accepts anything typed; quotes and -word work. Drafts only when asked."""
    text = (text or '').strip()
    if not text:
        return []

    config = cast('english', REGCONFIG)
    query = func.websearch_to_tsquery(config, text)
    rank = func.ts_rank(WikiArticle.search_vector, query)
    snippet = func.ts_headline(config, func.coalesce(WikiArticle.search_text, ''),
                               query, _HEADLINE_OPTIONS)

    stmt = (select(WikiArticle, WikiSection, snippet)
            .join(WikiSection, WikiArticle.section_id == WikiSection.id)
            .where(WikiArticle.search_vector.bool_op('@@')(query))
            .order_by(rank.desc(), WikiArticle.title)
            .limit(limit))
    if not include_drafts:
        stmt = stmt.where(WikiArticle.is_published.is_(True),
                          WikiSection.is_published.is_(True))

    return [SearchHit(article, section, highlight_snippet(raw))
            for article, section, raw in db.session.execute(stmt).all()]


def searchable_count(include_drafts=False):
    """How many articles a search covers for this reader."""
    stmt = (select(func.count(WikiArticle.id))
            .join(WikiSection, WikiArticle.section_id == WikiSection.id))
    if not include_drafts:
        stmt = stmt.where(WikiArticle.is_published.is_(True),
                          WikiSection.is_published.is_(True))
    return db.session.scalar(stmt)
