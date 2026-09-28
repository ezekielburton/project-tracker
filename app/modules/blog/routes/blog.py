from flask import (Blueprint, render_template, jsonify, request, abort, url_for, current_app,
                   get_template_attribute)
from flask_login import login_required, current_user
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import BlogPost, BlogComment
from app.modules.core.shared.lib.utils import get_actor, slugify
from app.modules.core.shared.lib.capabilities import can
from app.modules.core.shared.services.achievements import check_achievements
from datetime import datetime
import json, uuid, os

blog_bp = Blueprint('blog', __name__, template_folder='../templates')

_MEDIA_EXTENSIONS = {
    'png': 'image', 'jpg': 'image', 'jpeg': 'image', 'gif': 'image', 'webp': 'image',
    'mp4': 'video', 'webm': 'video',
}
_MEDIA_MAX_BYTES = 500 * 1024 * 1024


def _backup_post_media_to_nas(app, post_id):
    """Copies every image/video a post references to its NAS backup folder.
    Runs via _run_in_background (which supplies the app context). NAS errors
    are logged, never raised: local disk is the source of truth."""
    from app.modules.core.shared.services.nas import upload_app_file

    post = BlogPost.query.get(post_id)
    if not post:
        return

    folder = f'/Admin/OVP/blog/{post.id}-{slugify(post.title)}'
    upload_dir = os.path.join(app.root_path, 'static', 'blog-uploads')

    for section in json.loads(post.sections_json or '[]'):
        for block in section.get('blocks', []):
            if block.get('type') not in ('image', 'video'):
                continue
            filename = (block.get('url') or '').rsplit('/', 1)[-1]
            local_path = os.path.join(upload_dir, filename)
            if not filename or not os.path.isfile(local_path):
                continue
            try:
                with open(local_path, 'rb') as f:
                    upload_app_file(f.read(), folder, filename)
            except RuntimeError as e:
                app.logger.error(f'Blog media NAS backup failed for post {post.id}, file {filename}: {e}')


@blog_bp.route('/blog/upload-media', methods=['POST'])
@login_required
def upload_media():
    if not can('manage_blog', current_user):
        abort(403)

    file = request.files.get('file')
    if not file:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    kind = _MEDIA_EXTENSIONS.get(ext)
    if not kind:
        return jsonify({'success': False, 'error': 'File type not allowed'}), 400

    file_bytes = file.read()
    if len(file_bytes) > _MEDIA_MAX_BYTES:
        return jsonify({'success': False, 'error': f'File is too large (max {_MEDIA_MAX_BYTES // (1024 * 1024)}MB).'}), 400

    filename = f'{uuid.uuid4().hex}.{ext}'
    upload_dir = os.path.join(current_app.root_path, 'static', 'blog-uploads')
    os.makedirs(upload_dir, exist_ok=True)
    with open(os.path.join(upload_dir, filename), 'wb') as out:
        out.write(file_bytes)

    return jsonify({
        'success': True,
        'filename': filename,
        'url': url_for('static', filename=f'blog-uploads/{filename}'),
        'kind': kind
    })

@blog_bp.route('/blog')
@login_required
def index():
    posts = BlogPost.query.filter_by(is_published=True)\
     .order_by(BlogPost.published_at.desc()).all()

    if can('manage_blog', current_user):
        posts = BlogPost.query.order_by(BlogPost.created_at.desc()).all()

    return render_template('blog/index.html', posts=posts)

@blog_bp.route('/blog/post/<int:post_id>')
@login_required
def get_post(post_id):
    post = BlogPost.query.get_or_404(post_id)

    if not post.is_published and not can('manage_blog', current_user):
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

    if not post.is_published and not can('manage_blog', current_user):
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

    # Same avatar macro and delete rule as _post_content.html, so a comment
    # added in place looks like one rendered on load.
    user_avatar = get_template_attribute('_macros.html', 'user_avatar')
    return jsonify({
        'success': True,
        'comment': {
            'id': comment.id,
            'body': comment.body,
            'author': actor.name,
            'avatar_html': str(user_avatar(actor, 'sm')),
            'can_delete': can('manage_blog', actor),
            'parent_id': comment.parent_id,
            'created_at': comment.created_at.strftime('%d %b %Y, %H:%M')
        }
    })

@blog_bp.route('/blog/editor')
@login_required
def editor():
    if not can('manage_blog', current_user):
        abort(403)
    return render_template('blog/editor.html', post=None)

@blog_bp.route('/blog/editor/<int:post_id>')
@login_required
def editor_edit(post_id):
    if not can('manage_blog', current_user):
        abort(403)
    post = BlogPost.query.get_or_404(post_id)
    return render_template('blog/editor.html', post=post)

@blog_bp.route('/blog/posts', methods=['POST'])
@login_required
def create_post():
    if not can('manage_blog', current_user):
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
    new_post_id = post.id  # read once before the background task; avoids a concurrent lazy-load race

    from app.modules.core.shared.services.nas import _run_in_background
    _app_obj = current_app._get_current_object()
    _run_in_background(_app_obj, lambda: _backup_post_media_to_nas(_app_obj, new_post_id))

    return jsonify({'success': True, 'post_id': new_post_id})


@blog_bp.route('/blog/posts/<int:post_id>', methods=['PUT'])
@login_required
def update_post(post_id):
    if not can('manage_blog', current_user):
        abort(403)

    post = BlogPost.query.get_or_404(post_id)
    data = request.get_json()
    post.title = data['title']
    post.version_tag = data.get('version_tag', '')
    post.sections_json = json.dumps(data.get('sections', []))
    db.session.commit()

    from app.modules.core.shared.services.nas import _run_in_background
    _app_obj = current_app._get_current_object()
    # The route's post_id, not post.id: the thread must not lazy-load a request-bound object.
    _run_in_background(_app_obj, lambda: _backup_post_media_to_nas(_app_obj, post_id))

    # A draft's readers get told when it is published, not on every save.
    send_email = data.get('send_email', False)
    if send_email and post.is_published:
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
    if not can('manage_blog', current_user):
        abort(403)

    post = BlogPost.query.get_or_404(post_id)
    payload = request.get_json(silent=True) or {}
    was_published = post.is_published
    # published_at is set once and never cleared, so it marks the first publish.
    first_publish = post.published_at is None

    # An explicit 'publish' sets the state (the editor's Update & Publish must
    # not unpublish a live post); without it the button toggles.
    target = payload.get('publish')
    post.is_published = bool(target) if target is not None else not post.is_published
    if post.is_published and not post.published_at:
        post.published_at = datetime.utcnow()
    db.session.commit()

    send_email = payload.get('send_email', False)
    if post.is_published and not was_published and (first_publish or send_email):
        try:
            from app.modules.core.shared.services.notifications import notify_all_of_new_blog_post
            # Everyone gets the in-app notice once; a republish only emails when asked.
            notify_all_of_new_blog_post(post, current_user, send_inapp=first_publish, send_email=send_email)
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
    if not can('manage_blog', current_user):
        abort(403)

    comment = BlogComment.query.get_or_404(comment_id)
    # Replies point at their parent; delete them first or the FK blocks the delete.
    BlogComment.query.filter_by(parent_id=comment.id).delete()
    db.session.delete(comment)
    db.session.commit()
    return jsonify({'success': True})

@blog_bp.route('/blog/posts/<int:post_id>', methods=['DELETE'])
@login_required
def delete_post(post_id):
    if not can('manage_blog', current_user):
        abort(403)

    post = BlogPost.query.get_or_404(post_id)
    # Comments reference the post (replies reference comments); remove replies first.
    BlogComment.query.filter(BlogComment.post_id == post.id,
                             BlogComment.parent_id.isnot(None)).delete(synchronize_session=False)
    BlogComment.query.filter_by(post_id=post.id).delete(synchronize_session=False)
    db.session.delete(post)
    db.session.commit()
    return jsonify({'success': True})

@blog_bp.route('/blog-post1-v1.2update')
@login_required
def v12_update():
    # Hardcoded release-notes page, a template not a BlogPost; see blog.md "Known debt".
    return render_template('blog/v12_update.html')
