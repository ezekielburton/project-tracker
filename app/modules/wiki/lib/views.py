"""Reads of wiki articles: recorded once per person per article per day, and counted."""
from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import WikiArticleView

REPEAT_WINDOW = timedelta(hours=24)
MOST_READ_DAYS = 30
MOST_READ_SHOWN = 5


def record_view(article_id, user_id, source):
    """Count a read unless this person already read the article in the last day.
    Returns True when a new read was recorded."""
    since = datetime.utcnow() - REPEAT_WINDOW
    seen = (db.session.query(WikiArticleView.id)
            .filter(WikiArticleView.article_id == article_id, WikiArticleView.user_id == user_id,
                    WikiArticleView.viewed_at >= since)
            .first())
    if seen:
        return False
    db.session.add(WikiArticleView(article_id=article_id, user_id=user_id, source=source))
    db.session.commit()
    return True


def read_count(article_id):
    """All recorded reads of one article."""
    return db.session.scalar(
        select(func.count(WikiArticleView.id)).where(WikiArticleView.article_id == article_id))


def most_read(article_ids, days=MOST_READ_DAYS, limit=MOST_READ_SHOWN):
    """Of these articles, the most read in the window: (article_id, reads), most first. One query."""
    if not article_ids:
        return []
    since = datetime.utcnow() - timedelta(days=days)
    reads = func.count(WikiArticleView.id).label('reads')
    rows = db.session.execute(
        select(WikiArticleView.article_id, reads)
        .where(WikiArticleView.article_id.in_(article_ids), WikiArticleView.viewed_at >= since)
        .group_by(WikiArticleView.article_id)
        .order_by(reads.desc(), WikiArticleView.article_id)
        .limit(limit)
    ).all()
    return [(row.article_id, row.reads) for row in rows]
