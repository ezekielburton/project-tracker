"""The reader's rail and the panels beside an article."""
from datetime import datetime

from flask import url_for
from sqlalchemy.orm import selectinload

from app.modules.core.shared.models import WikiSection
from app.modules.wiki.lib.relevance import SCOPE_ALL, is_for, section_roles
from app.modules.wiki.lib.views import most_read

HOME_ICON = 'M3 11l9-7 9 7M5 10v10h14V10'
SEARCH_ICON = 'M11 4a7 7 0 1 0 0 14 7 7 0 1 0 0-14M20 20l-4-4'
RELATED_SHOWN = 3
START_FROM_EACH = 3
RECENT_SHOWN = 5


def readable_sections(include_drafts=False):
    """Each section with the articles this reader may open, in authored order.
    Sections with nothing to read are left out. Two queries, however many sections."""
    query = (WikiSection.query.options(selectinload(WikiSection.articles))
             .order_by(WikiSection.sort_order))
    if not include_drafts:
        query = query.filter(WikiSection.is_published.is_(True))
    pairs = []
    for section in query.all():
        articles = [article for article in section.articles if include_drafts or article.is_published]
        if articles:
            pairs.append((section, articles))
    return pairs


def rail_items(sections, role, scope, current_section_id=None, link_scope=None):
    """Home, Search, then each section with its articles. While scoped to the reader's
    role, other roles' sections start closed; the open article's section never does."""
    items = [
        {'key': 'home', 'label': 'Home', 'url': url_for('wiki.index', scope=link_scope), 'icon': HOME_ICON},
        {'key': 'search', 'label': 'Search', 'url': url_for('wiki.search', scope=link_scope), 'icon': SEARCH_ICON},
    ]
    for section, articles in sections:
        items.append({
            'key': f'section-{section.id}',
            'label': section.title,
            'url': url_for('wiki.index', scope=link_scope),
            'count': len(articles),
            'open': scope == SCOPE_ALL or is_for(section, role) or section.id == current_section_id,
            'children': [{'key': f'article-{article.id}', 'label': article.title,
                          'url': url_for('wiki.get_article', article_id=article.id, scope=link_scope)}
                         for article in articles],
        })
    return items


def related_articles(sections, article, limit=RELATED_SHOWN):
    """Other readable articles from the same section, in authored order."""
    for section, articles in sections:
        if section.id == article.section_id:
            return [other for other in articles if other.id != article.id][:limit]
    return []


def start_here(sections, role, per_section=START_FROM_EACH):
    """The reader's first articles: the first section for everyone, then the first
    section tagged with their role, a few from each in authored order. Pairs of (article, section)."""
    everyone = next(((section, articles) for section, articles in sections
                     if not section_roles(section)), None)
    mine = next(((section, articles) for section, articles in sections
                 if role in section_roles(section)), None)
    path = []
    for found in (everyone, mine):
        if found:
            section, articles = found
            path += [(article, section) for article in articles[:per_section]]
    return path


def recently_updated(sections, limit=RECENT_SHOWN):
    """The most recently updated readable articles, newest first. Pairs of (article, section)."""
    pairs = [(article, section) for section, articles in sections for article in articles]
    pairs.sort(key=lambda pair: pair[0].updated_at or datetime.min, reverse=True)
    return pairs[:limit]


def most_read_articles(sections):
    """The reader's most read articles this month, as (article, section, reads)."""
    found = {article.id: (article, section) for section, articles in sections for article in articles}
    return [found[article_id] + (reads,) for article_id, reads in most_read(list(found))]
