from flask import Blueprint, render_template, jsonify, request, abort
from flask_login import login_required, current_user
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import BlogPost, BlogComment, User
from app.modules.core.shared.lib.utils import get_actor
from app.modules.core.shared.services.achievements import check_achievements
from datetime import datetime
import json

blog_bp = Blueprint('blog', __name__, template_folder='../templates')

@blog_bp.route('/blog')
@login_required
def index():
    posts = BlogPost.query.filter_by(is_published=True)\
     .order_by(BlogPost.published_at.desc()).all()

    if current_user.role == 'admin':
        posts = BlogPost.query.order_by(BlogPost.created_at.desc()).all()

    return render_template('blog/index.html', posts=posts)

@blog_bp.route('/blog/post/<int:post_id>')
@login_required
def get_post(post_id):
    post = BlogPost.query.get_or_404(post_id)

    if not post.is_published and current_user.role != 'admin':
        abort(404)

    # Only top-level comments; replies are loaded via the backref
    comments = BlogComment.query.filter_by(post_id=post_id, parent_id=None)\
     .order_by(BlogComment.created_at.asc()).all()

    actor = get_actor()
    return render_template('blog/_post_content.html', post=post, comments=comments, actor=actor)

@blog_bp.route('/blog/post/<int:post_id>/comments', methods=['POST'])
@login_required
def add_comment(post_id):
    post = BlogPost.query.get_or_404(post_id)

    if not post.is_published and current_user.role != 'admin':
        abort(404)

    body = request.form.get('body', '').strip()
    parent_id = request.form.get('parent_id', type=int)

    if not body:
        return jsonify({'success': False, 'error': 'Comment cannot be empty'}), 400

    actor = get_actor()

    comment = BlogComment(
        post_id=post_id,
        user_id=actor.id,
        body=body,
        parent_id=parent_id
    )
    db.session.add(comment)
    db.session.commit()
    check_achievements(actor, 'blog_comment')

    return jsonify({
        'success': True,
        'comment': {
            'id': comment.id,
            'body': comment.body,
            'author': actor.name,
            'avatar_letter': actor.name[0].upper(),
            'parent_id': comment.parent_id,
            'created_at': comment.created_at.strftime('%d %b %Y, %H:%M')
        }
    })

@blog_bp.route('/blog/editor')
@login_required
def editor():
    if current_user.role != 'admin':
        abort(403)
    return render_template('blog/editor.html', post=None)

@blog_bp.route('/blog/editor/<int:post_id>')
@login_required
def editor_edit(post_id):
    if current_user.role != 'admin':
        abort(403)
    post = BlogPost.query.get_or_404(post_id)
    return render_template('blog/editor.html', post=post)

@blog_bp.route('/blog/posts', methods=['POST'])
@login_required
def create_post():
    if current_user.role != 'admin':
        abort(403)

    data = request.get_json()
    post = BlogPost(
        title=data['title'],
        version_tag=data.get('version_tag', ''),
        author_id=current_user.id,
        sections_json=json.dumps(data.get('sections', []))
    )
    db.session.add(post)
    db.session.commit()

    return jsonify({'success': True, 'post_id': post.id})


@blog_bp.route('/blog/posts/<int:post_id>', methods=['PUT'])
@login_required
def update_post(post_id):
    if current_user.role != 'admin':
        abort(403)

    post = BlogPost.query.get_or_404(post_id)
    data = request.get_json()
    post.title = data['title']
    post.version_tag = data.get('version_tag', '')
    post.sections_json = json.dumps(data.get('sections', []))
    db.session.commit()

    send_email = data.get('send_email', False)
    if send_email:
        try:
            from app.modules.core.shared.services.notifications import notify_all_of_new_blog_post
            notify_all_of_new_blog_post(post, current_user, send_inapp=False, send_email=True)
        except Exception:
            import traceback
            traceback.print_exc()
            # Email failure must not crash the response — post is already saved

    return jsonify({'success': True})

@blog_bp.route('/blog/posts/<int:post_id>/publish', methods=['POST'])
@login_required
def toggle_publish(post_id):
    if current_user.role != 'admin':
        abort(403)

    post = BlogPost.query.get_or_404(post_id)
    post.is_published = not post.is_published
    if post.is_published and not post.published_at:
        post.published_at = datetime.utcnow()
    db.session.commit()

    # Only notify when publishing (not unpublishing)
    if post.is_published:
        payload = request.get_json(silent=True) or {}
        send_email = payload.get('send_email', False)
        try:
            from app.modules.core.shared.services.notifications import notify_all_of_new_blog_post
            notify_all_of_new_blog_post(post, current_user, send_inapp=True, send_email=send_email)
        except Exception:
            import traceback
            traceback.print_exc()
            # Email failure must not crash the response — post is already published

    published_date = post.published_at.strftime('%d %b %Y') if post.published_at else ''

    return jsonify({
        'success': True,
        'is_published': post.is_published,
        'published_date': published_date
    })

@blog_bp.route('/blog/comments/<int:comment_id>', methods=['DELETE'])
@login_required
def delete_comment(comment_id):
    if current_user.role != 'admin':
        abort(403)

    comment = BlogComment.query.get_or_404(comment_id)
    db.session.delete(comment)
    db.session.commit()
    return jsonify({'success': True})

@blog_bp.route('/blog/posts/<int:post_id>', methods=['DELETE'])
@login_required
def delete_post(post_id):
    if current_user.role != 'admin':
        abort(403)

    post = BlogPost.query.get_or_404(post_id)
    db.session.delete(post)
    db.session.commit()
    return jsonify({'success': True})

@blog_bp.route('/blog-post1-v1.2update')
@login_required
def v12_update():
    # Static release-notes page for the v1.2 update: a single hardcoded page
    # kept as a template rather than a stored BlogPost. Owned here so the blog
    # module holds every blog URL; see blog.md "Known debt".
    return render_template('blog/v12_update.html')
