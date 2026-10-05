"""Searches that found nothing: recording them, counting them, and the Write next list."""
from collections import namedtuple
from datetime import datetime, timedelta

from sqlalchemy import cast, distinct, func, select, update
from sqlalchemy.dialects.postgresql import REGCONFIG

from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import WikiArticle, WikiSearchMiss, WikiSection

REPEAT_WINDOW = timedelta(hours=24)
NOTE_MAX = 500
NOTES_SHOWN = 3

Asked = namedtuple('Asked', 'times people')
WriteNextItem = namedtuple('WriteNextItem', 'key phrase times people last_at notes')


def _config():
    return cast('english', REGCONFIG)


def phrase_key(phrase):
    """The phrase's stemmed words, sorted and de-duplicated, so wordings of one
    question share a key. Empty when nothing in it is searchable."""
    words = func.tsvector_to_array(func.to_tsvector(_config(), phrase or ''))
    return db.session.scalar(select(func.array_to_string(words, ' '))) or ''


def record_miss(phrase, key, user_id):
    """Log a search that found nothing, once per person per question within a day.
    Returns the row that person's note attaches to."""
    since = datetime.utcnow() - REPEAT_WINDOW
    row = (WikiSearchMiss.query
           .filter(WikiSearchMiss.phrase_key == key, WikiSearchMiss.user_id == user_id,
                   WikiSearchMiss.created_at >= since)
           .order_by(WikiSearchMiss.created_at.desc())
           .first())
    if row is None:
        row = WikiSearchMiss(phrase=phrase[:200], phrase_key=key, user_id=user_id)
        db.session.add(row)
        db.session.commit()
    return row


def asked_counts(key, days=30):
    """How often a question was asked in the window, and by how many people."""
    since = datetime.utcnow() - timedelta(days=days)
    times, people = db.session.execute(
        select(func.count(WikiSearchMiss.id), func.count(distinct(WikiSearchMiss.user_id)))
        .where(WikiSearchMiss.phrase_key == key, WikiSearchMiss.created_at >= since)
    ).one()
    return Asked(times, people)


def write_next(days=90, limit=20):
    """Questions from the window that no published article answers yet, most asked
    first, shown in their most common wording. Dismissed rows are left out."""
    since = datetime.utcnow() - timedelta(days=days)
    miss = WikiSearchMiss
    grouped = (select(miss.phrase_key.label('key'),
                      func.count(miss.id).label('times'),
                      func.count(distinct(miss.user_id)).label('people'),
                      func.max(miss.created_at).label('last_at'),
                      func.mode().within_group(miss.phrase).label('phrase'))
               .where(miss.dismissed_at.is_(None), miss.created_at >= since)
               .group_by(miss.phrase_key)
               .subquery())
    answered = (select(WikiArticle.id)
                .join(WikiSection, WikiArticle.section_id == WikiSection.id)
                .where(WikiArticle.is_published.is_(True), WikiSection.is_published.is_(True),
                       WikiArticle.search_vector.bool_op('@@')(
                           func.websearch_to_tsquery(_config(), grouped.c.phrase))))
    rows = db.session.execute(
        select(grouped)
        .where(~answered.exists())
        .order_by(grouped.c.times.desc(), grouped.c.last_at.desc())
        .limit(limit)
    ).all()

    notes = {}
    keys = [row.key for row in rows]
    if keys:
        for key, note in db.session.execute(
                select(miss.phrase_key, miss.note)
                .where(miss.phrase_key.in_(keys), miss.note.isnot(None),
                       miss.dismissed_at.is_(None), miss.created_at >= since)
                .order_by(miss.created_at.desc())):
            kept = notes.setdefault(key, [])
            if len(kept) < NOTES_SHOWN:
                kept.append(note)

    return [WriteNextItem(row.key, row.phrase, row.times, row.people, row.last_at,
                          notes.get(row.key, [])) for row in rows]


def dismiss(key):
    """Take a question off Write next. Asking it again later puts it back."""
    db.session.execute(
        update(WikiSearchMiss)
        .where(WikiSearchMiss.phrase_key == key, WikiSearchMiss.dismissed_at.is_(None))
        .values(dismissed_at=datetime.utcnow())
    )
    db.session.commit()
