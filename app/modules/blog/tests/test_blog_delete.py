"""Deleting a blog post or comment that others' comments hang off."""
from app.modules.core.shared.models import BlogComment, BlogPost, User
from app.modules.core.shared.testing import login_as


def _setup(db_session, tag):
    admin = User(name=f'Blog del {tag}', email=f'blog-del-{tag}@example.com', role='admin')
    admin.set_password('password123')
    db_session.add(admin)
    db_session.flush()
    post = BlogPost(title='Delete test', author_id=admin.id, sections_json='[]')
    db_session.add(post)
    db_session.flush()
    parent = BlogComment(post_id=post.id, user_id=admin.id, body='parent')
    db_session.add(parent)
    db_session.flush()
    reply = BlogComment(post_id=post.id, user_id=admin.id, body='reply', parent_id=parent.id)
    db_session.add(reply)
    db_session.flush()
    return admin, post, parent


def test_deleting_a_post_with_comments_removes_them(app, client, db_session):
    admin, post, _ = _setup(db_session, 'post')
    post_id = post.id
    login_as(client, app, admin, 'password123')

    resp = client.delete(f'/blog/posts/{post_id}')

    assert resp.status_code == 200
    assert BlogPost.query.get(post_id) is None
    assert BlogComment.query.filter_by(post_id=post_id).count() == 0


def test_deleting_a_comment_with_replies_removes_the_replies(app, client, db_session):
    admin, post, parent = _setup(db_session, 'comment')
    parent_id = parent.id
    login_as(client, app, admin, 'password123')

    resp = client.delete(f'/blog/comments/{parent_id}')

    assert resp.status_code == 200
    assert BlogComment.query.filter_by(post_id=post.id).count() == 0
