import json, re, uuid, os
from datetime import datetime
from flask import (Blueprint, render_template, request, jsonify, abort, redirect, url_for, current_app)
from flask_login import login_required, current_user
from app import db
from app.models import WikiSection, WikiArticle
from app.decorators import role_required

wiki_bp = Blueprint('wiki', __name__)

# ------ Helper ------

def _slugify(text):
    """Convert a title to a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    return re.sub(r'-+', '-', text).strip('-')

# ------ Viewer ------

@wiki_bp.route('/wiki')
@login_required
def index():
    if current_user.role == 'admin':
        sections = WikiSection.query.order_by(WikiSection.sort_order).all()
    else:
        sections = (WikiSection.query.filter_by(is_published=True).order_by(WikiSection.sort_order).all())
    return render_template('wiki/index.html', sections=sections)

@wiki_bp.route('/wiki/article/<int:article_id>')
@login_required
def get_article(article_id):
    article = WikiArticle.query.get_or_404(article_id)
    if not article.is_published and current_user.role != 'admin':
        abort(403)
    blocks = json.loads(article.sections_json or '[]')
    return render_template('wiki/_article_content.html', article=article, blocks=blocks)

#------ Image upload & serve ------

@wiki_bp.route('/wiki/upload-image', methods=['POST'])
@login_required
@role_required('admin')
def upload_image():
    file = request.files.get('file')
    if not file:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    ext = file.filename.rsplit ('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in {'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'}:
        return jsonify({'success': False, 'error': 'File type not allowed'}), 400
    
    filename = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = os.path.join(current_app.root_path, 'static', 'wiki-uploads')
    os.makedirs(upload_dir, exist_ok=True)
    file.save(os.path.join(upload_dir, filename))

    return jsonify({
        'success': True,
        'filename': filename,
        'url': url_for('static', filename=f'wiki-uploads/{filename}')
    })


# ------ Editor Sections ------
@wiki_bp.route('/wiki/editor')
@login_required
@role_required('admin')
def editor_dashboard(): 
    sections = WikiSection.query.order_by(WikiSection.sort_order).all()
    return render_template('wiki/editor_dashboard.html', sections=sections)

@wiki_bp.route('/wiki/editor/section/new')
@login_required
@role_required('admin')
def new_section():
    sections = WikiSection.query.order_by(WikiSection.sort_order).all()
    return render_template('wiki/editor_section.html', section=None)

@wiki_bp.route('/wiki/editor/article/<int:article_id>/edit')
@login_required
@role_required('admin')
def edit_article(article_id):
    article = WikiArticle.query.get_or_404(article_id)
    return render_template('wiki/editor_article.html', article=article, section=article.section)


@wiki_bp.route('/wiki/editor/article/save', methods=['POST'])
@login_required
@role_required('admin')
def save_article():
    article_id    = request.form.get('article_id', '').strip()
    section_id    = request.form.get('section_id', '').strip()
    title         = request.form.get('title', '').strip()
    slug          = request.form.get('slug', '').strip() or _slugify(title)
    sections_json = request.form.get('sections_json', '[]')
    sort_order    = int(request.form.get('sort_order', 0))

    if not title or not section_id:
        return jsonify({'success': False, 'error': 'Title and section are required'}), 400

    try:
        json.loads(sections_json)
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid content data'}), 400

    if article_id:
        article               = WikiArticle.query.get_or_404(int(article_id))
        article.section_id    = int(section_id)
        article.title         = title
        article.slug          = slug
        article.sections_json = sections_json
        article.sort_order    = sort_order
        article.updated_at    = datetime.utcnow()
    else:
        article = WikiArticle(section_id=int(section_id), title=title,
                              slug=slug, sections_json=sections_json,
                              sort_order=sort_order)
        db.session.add(article)

    db.session.commit()
    return redirect(url_for('wiki.edit_article', article_id=article.id))


@wiki_bp.route('/wiki/editor/article/<int:article_id>/toggle-publish', methods=['POST'])
@login_required
@role_required('admin')
def toggle_article_publish(article_id):
    article = WikiArticle.query.get_or_404(article_id)
    article.is_published = not article.is_published
    db.session.commit()
    return jsonify({'success': True, 'is_published': article.is_published})


@wiki_bp.route('/wiki/editor/article/<int:article_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_article(article_id):
    article = WikiArticle.query.get_or_404(article_id)
    db.session.delete(article)
    db.session.commit()
    return jsonify({'success': True})

@wiki_bp.route('/wiki/editor/article/new')
@login_required
@role_required('admin')
def new_article():
    section_id = request.args.get('section_id')
    section = WikiSection.query.get_or_404(int(section_id)) if section_id else None
    return render_template('wiki/editor_article.html', article=None, section=section)


@wiki_bp.route('/wiki/editor/section/<int:section_id>/edit')
@login_required
@role_required('admin')
def edit_section(section_id):
    section = WikiSection.query.get_or_404(section_id)
    return render_template('wiki/editor_section.html', section=section)


@wiki_bp.route('/wiki/editor/section/save', methods=['POST'])
@login_required
@role_required('admin')
def save_section():
    section_id     = request.form.get('section_id', '').strip()
    title          = request.form.get('title', '').strip()
    slug           = request.form.get('slug', '').strip() or _slugify(title)
    relevant_roles = ','.join(request.form.getlist('relevant_roles'))
    sort_order     = int(request.form.get('sort_order', 0))

    if not title:
        return redirect(url_for('wiki.editor_dashboard'))

    if section_id:
        section                = WikiSection.query.get_or_404(int(section_id))
        section.title          = title
        section.slug           = slug
        section.relevant_roles = relevant_roles or None
        section.sort_order     = sort_order
    else:
        section = WikiSection(
            title=title, slug=slug,
            relevant_roles=relevant_roles or None,
            sort_order=sort_order
        )
        db.session.add(section)

    db.session.commit()
    return redirect(url_for('wiki.editor_dashboard'))


@wiki_bp.route('/wiki/editor/section/<int:section_id>/toggle-publish', methods=['POST'])
@login_required
@role_required('admin')
def toggle_section_publish(section_id):
    section = WikiSection.query.get_or_404(section_id)
    section.is_published = not section.is_published
    db.session.commit()
    return jsonify({'success': True, 'is_published': section.is_published})


@wiki_bp.route('/wiki/editor/section/<int:section_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_section(section_id):
    section = WikiSection.query.get_or_404(section_id)
    db.session.delete(section)
    db.session.commit()
    return jsonify({'success': True})