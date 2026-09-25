"""The help-key registry, the coverage figures, and the contract with templates."""
import json
import os
import re

from app.modules.core.shared.models import User, WikiArticle, WikiSection
from app.modules.core.shared.testing import login_as
from app.modules.wiki.lib.help_keys import (
    HELP_KEY_GROUPS, HELP_KEY_LABELS, HELP_KEYS, coverage, is_registered, label_for,
)

APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*(\.[a-z0-9_-]+)+$')
# Both ways a page can name a key: the macro call, and a hand-written attribute.
# Values built from a variable are skipped — there is no literal to check.
USED_IN_TEMPLATE = re.compile(r'''help_button\(\s*['"]([^'"]+)['"]|data-help-key="([^"{}]+)"''')


def _user(app, client, db_session, email, role='admin'):
    user = User(name=email.split('@')[0], email=email, role=role)
    user.set_password('pw123456')
    db_session.add(user)
    db_session.commit()
    login_as(client, app, user, 'pw123456')
    return user


def _article(db_session, section, slug, help_key=None, title='A'):
    article = WikiArticle(section_id=section.id, title=title, slug=slug, help_key=help_key,
                          sections_json=json.dumps({'time': 0, 'version': '2.30.7', 'blocks': []}))
    db_session.add(article)
    db_session.commit()
    return article


# ------ The registry itself ------

def test_every_key_is_well_formed():
    for key in HELP_KEYS:
        assert KEY_PATTERN.match(key), f'{key} is not a lowercase dotted key'


def test_no_key_appears_twice():
    keys = [key for _, pairs in HELP_KEY_GROUPS for key, _ in pairs]
    assert len(keys) == len(set(keys)), 'a help key is registered in two groups'


def test_every_key_has_a_label():
    for key in HELP_KEYS:
        assert HELP_KEY_LABELS[key].strip()


def test_label_for_falls_back_to_the_key():
    assert label_for('not.registered') == 'not.registered'


# ------ The contract with the app's templates ------

def test_every_help_key_used_in_a_template_is_registered():
    """
    A key used on a page but missing from the registry renders a dead "?" with
    no error anywhere. This catches it at test time instead.
    """
    unregistered = []
    for root, _, files in os.walk(os.path.join(APP_DIR, 'modules')):
        for name in files:
            if not name.endswith('.html'):
                continue
            path = os.path.join(root, name)
            for found in USED_IN_TEMPLATE.findall(open(path, encoding='utf-8').read()):
                key = next(group for group in found if group)
                if not is_registered(key):
                    unregistered.append(f'{key} (in {os.path.relpath(path, APP_DIR)})')

    assert not unregistered, (
        'These pages declare a help key that is not in lib/help_keys.py. '
        'Register the key, or fix the typo on the page: ' + '; '.join(unregistered)
    )


# ------ Coverage figures ------

def test_coverage_counts_only_registered_keys():
    result = coverage(['core.overview', 'made.up.key', None])
    assert result['written'] == 1
    assert result['total'] == len(HELP_KEYS)


def test_coverage_lists_every_unwritten_key():
    result = coverage([])
    assert len(result['missing']) == len(HELP_KEYS)
    assert all(set(entry) == {'key', 'label', 'group'} for entry in result['missing'])


def test_coverage_group_scores_add_up():
    result = coverage(['core.overview', 'core.roles'])
    started = next(g for g in result['groups'] if g['name'] == 'Getting started')
    assert (started['written'], started['total']) == (2, 4)


# ------ Claiming a key ------

def test_creating_an_article_claims_its_key(app, client, db_session):
    _user(app, client, db_session, 'key-create@example.com')
    section = WikiSection(title='S', slug='k-create')
    db_session.add(section)
    db_session.commit()

    client.post('/wiki/editor/article/create', data={
        'section_id': str(section.id), 'title': 'Submitting a draft',
        'template': 'blank', 'help_key': 'projects.submissions',
    })

    assert WikiArticle.query.first().help_key == 'projects.submissions'


def test_an_unregistered_key_is_refused(app, client, db_session):
    _user(app, client, db_session, 'key-bogus@example.com')
    section = WikiSection(title='S', slug='k-bogus')
    db_session.add(section)
    db_session.commit()

    client.post('/wiki/editor/article/create', data={
        'section_id': str(section.id), 'title': 'Nope', 'template': 'blank',
        'help_key': 'totally.made.up',
    })

    assert WikiArticle.query.first().help_key is None


def test_a_key_moves_rather_than_being_shared(app, client, db_session):
    """Two articles on one key would make the "?" ambiguous, so the newer wins."""
    _user(app, client, db_session, 'key-move@example.com')
    section = WikiSection(title='S', slug='k-move')
    db_session.add(section)
    db_session.commit()
    first = _article(db_session, section, 'k-first', help_key='cs.invoicing', title='First')
    second = _article(db_session, section, 'k-second', title='Second')

    client.post('/wiki/editor/article/save', data={
        'article_id': str(second.id), 'section_id': str(section.id), 'title': 'Second',
        'help_key': 'cs.invoicing',
        'sections_json': json.dumps({'time': 0, 'version': '2.30.7', 'blocks': []}),
    })
    db_session.expire_all()

    assert WikiArticle.query.get(second.id).help_key == 'cs.invoicing'
    assert WikiArticle.query.get(first.id).help_key is None

def test_the_article_losing_a_key_keeps_its_updated_at(app, client, db_session):
    """Losing a key is not an edit, so the reader's Last Updated must not move."""
    _user(app, client, db_session, 'key-move-date@example.com')
    section = WikiSection(title='S', slug='k-move-date')
    db_session.add(section)
    db_session.commit()
    first = _article(db_session, section, 'k-date-first', help_key='cs_closed', title='First')
    second = _article(db_session, section, 'k-date-second', title='Second')
    was_updated_at = first.updated_at

    client.post('/wiki/editor/article/save', data={
        'article_id': str(second.id), 'section_id': str(section.id), 'title': 'Second',
        'help_key': 'cs_closed',
        'sections_json': json.dumps({'time': 0, 'version': '2.30.7', 'blocks': []}),
    })
    db_session.expire_all()

    assert WikiArticle.query.get(first.id).help_key is None
    assert WikiArticle.query.get(first.id).updated_at == was_updated_at




