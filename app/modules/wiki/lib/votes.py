"""The "Useful?" vote: one answer per person per article, and the articles marked not useful."""
from collections import namedtuple
from datetime import datetime

from sqlalchemy import func, select

from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import WikiArticle, WikiArticleVote

NOTE_MAX = 500
NOTES_SHOWN = 3
NOT_USEFUL_SHOWN = 20

NotUseful = namedtuple('NotUseful', 'article noes last_at notes')


def current_vote(article_id, user_id):
    return WikiArticleVote.query.filter_by(article_id=article_id, user_id=user_id).first()


def cast_vote(article_id, user_id, helpful, note=''):
    """Record or change a person's answer. A yes clears any note; a no keeps one when given."""
    vote = current_vote(article_id, user_id)
    if vote is None:
        vote = WikiArticleVote(article_id=article_id, user_id=user_id, helpful=helpful)
        db.session.add(vote)
    vote.helpful = helpful
    note = (note or '').strip()[:NOTE_MAX]
    if helpful:
        vote.note = None
    elif note:
        vote.note = note
    vote.updated_at = datetime.utcnow()
    db.session.commit()
    return vote


def not_useful(limit=NOT_USEFUL_SHOWN):
    """Articles with "no" answers given since the article was last saved, most noes first.
    Saving the article clears it from the list. Two queries, however many articles."""
    vote = WikiArticleVote
    noes = func.count(vote.id).label('noes')
    last_at = func.max(vote.updated_at).label('last_at')
    rows = db.session.execute(
        select(WikiArticle, noes, last_at)
        .join(vote, vote.article_id == WikiArticle.id)
        .where(vote.helpful.is_(False), vote.updated_at > WikiArticle.updated_at)
        .group_by(WikiArticle.id)
        .order_by(noes.desc(), last_at.desc())
        .limit(limit)
    ).all()

    notes = {}
    ids = [article.id for article, _, _ in rows]
    if ids:
        for article_id, note in db.session.execute(
                select(vote.article_id, vote.note)
                .join(WikiArticle, WikiArticle.id == vote.article_id)
                .where(vote.article_id.in_(ids), vote.helpful.is_(False), vote.note.isnot(None),
                       vote.updated_at > WikiArticle.updated_at)
                .order_by(vote.updated_at.desc())):
            kept = notes.setdefault(article_id, [])
            if len(kept) < NOTES_SHOWN:
                kept.append(note)

    return [NotUseful(article, count, at, notes.get(article.id, [])) for article, count, at in rows]
