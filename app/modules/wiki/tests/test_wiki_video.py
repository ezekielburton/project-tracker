"""Video first: the first video leads the article, and its length is cleaned and shown."""
import json

import pytest

from app.modules.core.shared.models import User, WikiArticle, WikiSection
from app.modules.core.shared.testing import login_as
from app.modules.wiki.lib.blocks import (
    first_video_length, format_length, lead_with_video, load_blocks, sanitize_document,
)

PW = 'pw123456'
VIDEO = {'id': 'v', 'type': 'helixVideo', 'data': {'source': 'embed', 'url': 'https://youtu.be/abc', 'length': 80}}
PARA = {'id': 'p', 'type': 'paragraph', 'data': {'text': 'Read the steps'}}


def _document(*blocks):
    return {'time': 0, 'version': '2.30.7', 'blocks': list(blocks)}


def _video(length):
    return _document({'id': 'v', 'type': 'helixVideo',
                      'data': {'source': 'embed', 'url': 'https://youtu.be/abc', 'length': length}})


# ------ The length ------

@pytest.mark.parametrize('given, kept', [
    (80, 80), ('75', 75), (3600, 3600),
    (0, None), (-5, None), (99999, None), ('abc', None), (True, None), (None, None),
])
def test_the_save_cleaner_keeps_only_a_sensible_length(given, kept):
    data = sanitize_document(_video(given))['blocks'][0]['data']
    assert data.get('length') == kept


def test_the_length_is_checked_again_on_read():
    blocks = load_blocks(json.dumps(_video(99999)))
    assert blocks[0]['data']['length'] is None


def test_first_video_length_reads_the_stored_document():
    assert first_video_length(json.dumps(_document(PARA, VIDEO))) == 80
    assert first_video_length(json.dumps(_document(PARA))) is None
    assert first_video_length('not json') is None


@pytest.mark.parametrize('seconds, text', [(40, '40s'), (80, '1m 20s'), (120, '2m'), (None, '')])
def test_format_length(seconds, text):
    assert format_length(seconds) == text


# ------ Video first ------

def test_the_first_video_moves_to_the_top_and_the_rest_keep_their_order():
    blocks = [{'type': 'paragraph', 'n': 1}, {'type': 'helixVideo', 'n': 2},
              {'type': 'paragraph', 'n': 3}, {'type': 'helixVideo', 'n': 4}]
    assert [b['n'] for b in lead_with_video(blocks)] == [2, 1, 3, 4]
    assert lead_with_video([{'type': 'paragraph'}]) == [{'type': 'paragraph'}]


def _setup(db_session):
    user = User(name='Video Reader', email='video-reader@example.com', role='designer')
    user.set_password(PW)
    section = WikiSection(title='Videos', slug='video-section', is_published=True)
    db_session.add_all([user, section])
    db_session.commit()
    article = WikiArticle(section_id=section.id, title='Watch first', slug='watch-first',
                          sections_json=json.dumps(_document(PARA, VIDEO)), is_published=True)
    db_session.add(article)
    db_session.commit()
    return user, article


@pytest.mark.parametrize('url', ['/wiki/article/{id}', '/wiki/help/article/{id}'])
def test_the_reader_and_the_tray_lead_with_the_video(app, db_session, url):
    user, article = _setup(db_session)
    client = app.test_client()
    login_as(client, app, user, PW)

    body = client.get(url.format(id=article.id)).get_data(as_text=True)

    assert body.index('<iframe') < body.index('Read the steps')
    assert 'class="wiki-block-video__length">1m 20s<' in body


def test_start_here_shows_the_video_length(app, db_session):
    user, _ = _setup(db_session)
    client = app.test_client()
    login_as(client, app, user, PW)

    assert '1m 20s video' in client.get('/wiki').get_data(as_text=True)
