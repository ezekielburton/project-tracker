from flask import Blueprint, render_template, jsonify, request, abort, url_for, current_app
from flask_login import login_required, current_user
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import BlogPost, BlogComment, User
from app.modules.core.shared.lib.utils import get_actor, slugify
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
    Called via _run_in_background, which already provides the app context —
    a NAS failure here is logged only, never raised, since local disk is the
    source of truth for blog media."""
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
    if current_user.role != 'admin':
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

    from app.modules.core.shared.services.nas import _run_in_background
    _app_obj = current_app._get_current_object()
    _run_in_background(_app_obj, lambda: _backup_post_media_to_nas(_app_obj, post.id))

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

    from app.modules.core.shared.services.nas import _run_in_background
    _app_obj = current_app._get_current_object()
    _run_in_background(_app_obj, lambda: _backup_post_media_to_nas(_app_obj, post.id))

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
