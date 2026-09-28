"""Publishing, republishing and saving a blog post: who gets told, and when.

Key rule: everyone gets one in-app notice per post, on its first publish.
"""
import json

from app.modules.core.shared.models import BlogPost, User
from app.modules.core.shared.services import nas as nas_module
from app.modules.core.shared.services import notifications as notifications_module
from app.modules.core.shared.testing import login_as
import app.modules.blog.routes.blog as blog_module


def _admin(db_session, tag):
    user = User(name=f'Blog {tag}', email=f'blog-pub-{tag}@example.com', role='admin')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _post(db_session, author, **kwargs):
    post = BlogPost(title='Publish test', author_id=author.id, sections_json='[]', **kwargs)
    db_session.add(post)
    db_session.flush()
    return post


def _record_notifies(monkeypatch):
    calls = []
    monkeypatch.setattr(notifications_module, 'notify_all_of_new_blog_post',
                        lambda post, by, send_inapp=True, send_email=True:
                        calls.append({'send_inapp': send_inapp, 'send_email': send_email}))
    return calls


def test_republishing_does_not_notify_everyone_again(app, client, db_session, monkeypatch):
    admin = _admin(db_session, 'republish')
    post = _post(db_session, admin)
    calls = _record_notifies(monkeypatch)
    login_as(client, app, admin, 'password123')

    url = f'/blog/posts/{post.id}/publish'
    assert client.post(url).get_json()['is_published'] is True
    assert client.post(url).get_json()['is_published'] is False
    assert client.post(url).get_json()['is_published'] is True

    assert calls == [{'send_inapp': True, 'send_email': False}]


def test_update_and_publish_keeps_a_live_post_live(app, client, db_session, monkeypatch):
    admin = _admin(db_session, 'keep-live')
    post = _post(db_session, admin)
    calls = _record_notifies(monkeypatch)
    login_as(client, app, admin, 'password123')

    url = f'/blog/posts/{post.id}/publish'
    client.post(url, json={'publish': True, 'send_email': True})
    data = client.post(url, json={'publish': True, 'send_email': True}).get_json()

    assert data['is_published'] is True
    assert len(calls) == 1


def test_saving_a_draft_sends_no_email(app, client, db_session, monkeypatch):
    admin = _admin(db_session, 'draft-save')
    post = _post(db_session, admin)
    calls = _record_notifies(monkeypatch)
    monkeypatch.setattr(nas_module, '_run_in_background', lambda app_obj, fn: None)
    login_as(client, app, admin, 'password123')

    client.put(f'/blog/posts/{post.id}', json={'title': 'Draft', 'sections': [], 'send_email': True})
    assert calls == []


def test_update_backup_task_does_not_read_the_request_bound_post(app, client, db_session, monkeypatch):
    """The backup runs on a thread after the request; by then the post object
    is expired and detached, so the task must carry a plain id."""
    admin = _admin(db_session, 'backup-id')
    post = _post(db_session, admin)
    post_id = post.id
    tasks, backed_up = [], []
    monkeypatch.setattr(nas_module, '_run_in_background', lambda app_obj, fn: tasks.append(fn))
    monkeypatch.setattr(blog_module, '_backup_post_media_to_nas',
                        lambda app_obj, pid: backed_up.append(pid))
    login_as(client, app, admin, 'password123')

    client.put(f'/blog/posts/{post_id}', json={'title': 'T', 'sections': []})
    db_session.expunge_all()
    tasks[0]()

    assert backed_up == [post_id]


def test_new_comment_json_carries_the_template_avatar(app, client, db_session):
    admin = _admin(db_session, 'comment')
    post = _post(db_session, admin, is_published=True)
    login_as(client, app, admin, 'password123')

    c = client.post(f'/blog/post/{post.id}/comments', data={'body': '<b>hi</b>'}).get_json()['comment']
    assert 'user-avatar-link' in c['avatar_html']
    assert c['can_delete'] is True
    assert c['body'] == '<b>hi</b>'  # escaped client-side, like the template does
