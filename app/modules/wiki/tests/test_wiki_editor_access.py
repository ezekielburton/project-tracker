"""Who may reach the wiki editor: real admins only, never through emulation."""
import os

import pytest

from app.modules.core.shared.models import User, WikiArticle, WikiSection
from app.modules.core.shared.testing import login_as

APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
BASELINE = os.path.join(os.path.dirname(APP_DIR), 'refactor', 'route_baseline.txt')
UPLOADS = ('/wiki/upload-image', '/wiki/upload-video')


def _gated_rules():
    """Read the route list from the committed baseline, so a new editor route
    joins this test the moment it is added rather than slipping past ungated."""
    rules = []
    for line in open(BASELINE, encoding='utf-8'):
        parts = line.rstrip('\n').split('\t')
        if len(parts) != 3:
            continue
        rule, methods, endpoint = parts
        if endpoint.startswith('wiki.') and (rule.startswith('/wiki/editor') or rule in UPLOADS):
            rules.append((rule, methods))
    return rules


GATED_RULES = _gated_rules()


def _user(app, db_session, email, role):
    user = User(name=email.split('@')[0], email=email, role=role)
    user.set_password('pw123456')
    db_session.add(user)
    db_session.commit()
    return user


def _fixture_rows(db_session):
    section = WikiSection(title='Gate', slug='gate-section')
    db_session.add(section)
    db_session.commit()
    article = WikiArticle(section_id=section.id, title='Gate', slug='gate-article',
                          sections_json='{"time": 0, "version": "2.30.7", "blocks": []}')
    db_session.add(article)
    db_session.commit()
    return section, article


def _call(app, user, rule, methods, section, article, emulating=None):
    """Each leg gets its own client, so one login never leaks into the next."""
    path = (rule.replace('<int:section_id>', str(section.id))
                .replace('<int:article_id>', str(article.id)))
    client = app.test_client()
    login_as(client, app, user, 'pw123456')
    if emulating is not None:
        with client.session_transaction() as sess:
            sess['emulating_user_id'] = emulating.id
    return client.post(path) if 'POST' in methods else client.get(path)


def test_the_baseline_actually_yielded_routes():
    assert len(GATED_RULES) >= 14, 'the editor route list came back empty or short'


def _assert_through(resp, rule, who):
    assert resp.status_code not in (401, 403), f'{rule} shut out {who}'
    assert resp.status_code < 500, f'{rule} blew up for {who} ({resp.status_code})'


@pytest.mark.parametrize('rule, methods', GATED_RULES, ids=[r for r, _ in GATED_RULES])
def test_editor_route_is_admin_only(app, db_session, rule, methods):
    """The gate reads the logged-in user, not the emulated one: emulation can
    never let someone in, and never shuts a real admin out mid-preview."""
    section, article = _fixture_rows(db_session)
    designer = _user(app, db_session, 'gate-designer@example.com', 'designer')
    admin = _user(app, db_session, 'gate-admin@example.com', 'admin')

    assert _call(app, designer, rule, methods, section, article).status_code == 403, \
        f'{rule} let a designer in'

    assert _call(app, designer, rule, methods, section, article,
                 emulating=admin).status_code == 403, \
        f'{rule} let a designer in by claiming to emulate an admin'

    _assert_through(_call(app, admin, rule, methods, section, article),
                    rule, 'a real admin')

    _assert_through(_call(app, admin, rule, methods, section, article, emulating=designer),
                    rule, 'an admin emulating a designer')