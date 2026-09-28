"""Notification emails: the project button link and escaping of user-typed
text in the HTML body.
"""
from types import SimpleNamespace

import pytest

from app.modules.core.shared.extensions import mail
from app.modules.core.shared.models import User
from app.modules.core.shared.services import notifications as svc

XSS = '<script>alert(1)</script>'


@pytest.fixture()
def sent_mail(app, db_session, monkeypatch):
    """Turn mail on and capture messages instead of sending them."""
    outbox = []
    monkeypatch.setitem(app.config, 'MAIL_ENABLED', True)
    monkeypatch.setattr(mail, 'send', outbox.append)
    return outbox


def _user(db_session, tag, name=None):
    user = User(name=name or f'Notif {tag}', email=f'notif-{tag}@example.com', role='designer')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def test_email_button_opens_the_project_in_the_projects_list(sent_mail):
    recipient = SimpleNamespace(name='Ann', email='ann@example.com')
    project = SimpleNamespace(id=4242, name='Summer POSM')

    svc._send_notification_email(recipient, 'Something happened.', project)

    html = sent_mail[0].html
    assert 'https://app.vitamin-e.work/projects-new/?project=4242' in html
    assert '/projects/4242' not in html


def test_email_escapes_message_project_and_recipient_names(sent_mail):
    recipient = SimpleNamespace(name='<i>Ann</i>', email='ann@example.com')
    project = SimpleNamespace(id=1, name='<b>Bold</b>')

    svc._send_notification_email(recipient, f'Flag: {XSS}', project)

    html = sent_mail[0].html
    assert XSS not in html
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html
    assert '<b>Bold</b>' not in html and '&lt;b&gt;Bold&lt;/b&gt;' in html
    assert '<i>Ann</i>' not in html and '&lt;i&gt;Ann&lt;/i&gt;' in html
    # The plain-text part stays unescaped.
    assert XSS in sent_mail[0].body


def test_feedback_email_escapes_title_and_submitter(sent_mail):
    submitter = SimpleNamespace(name='<i>Bo</i>')

    svc.notify_admin_of_new_feedback('Bug Report', XSS, submitter, '/feedback')

    html = sent_mail[0].html
    assert XSS not in html and '&lt;script&gt;' in html
    assert '<i>Bo</i>' not in html


def test_blog_email_escapes_post_title(app, db_session, sent_mail, monkeypatch):
    author = _user(db_session, 'blog-author')
    _user(db_session, 'blog-reader')

    # Run the background email thread inline.
    class _InlineThread:
        def __init__(self, target, daemon=None):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr('threading.Thread', _InlineThread)
    post = SimpleNamespace(id=7, title=XSS, version_tag='<v2>')

    svc.notify_all_of_new_blog_post(post, author, send_inapp=False)

    assert sent_mail
    for msg in sent_mail:
        assert XSS not in msg.html and '&lt;script&gt;' in msg.html
        assert '<v2>' not in msg.html

