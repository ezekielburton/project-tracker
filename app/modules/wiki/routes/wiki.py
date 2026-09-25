import json, uuid, os
from datetime import datetime
from flask import (Blueprint, render_template, request, jsonify, abort, redirect, url_for, current_app, flash)
from flask_login import login_required
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import WikiSection, WikiArticle
from app.modules.core.shared.lib.capabilities import can, require
from app.modules.core.shared.lib.utils import slugify
from sqlalchemy import update
from app.modules.wiki.lib.blocks import load_blocks, sanitize_document, empty_document
from app.modules.wiki.lib.article_templates import picker_options, template_document
from app.modules.wiki.lib.help_keys import HELP_KEY_GROUPS, coverage, is_registered, label_for

wiki_bp = Blueprint('wiki', __name__, template_folder='../templates')

# ------ Viewer ------

@wiki_bp.route('/wiki')
@login_required
def index():
    if can('manage_wiki'):
        sections = WikiSection.query.order_by(WikiSection.sort_order).all()
    else:
        sections = (WikiSection.query.filter_by(is_published=True).order_by(WikiSection.sort_order).all())
    return render_template('wiki/index.html', sections=sections)

@wiki_bp.route('/wiki/article/<int:article_id>')
@login_required
def get_article(article_id):
    article = WikiArticle.query.get_or_404(article_id)
    if not article.is_published and not can('manage_wiki'):
        abort(403)
    blocks = load_blocks(article.sections_json)
    return render_template('wiki/_article_content.html', article=article, blocks=blocks)

# ------ Contextual help (the "?" tray) ------

@wiki_bp.route('/wiki/help')
@login_required
def help_browse():
    """Everything there is to read — the Help pill opened with no key."""
    if can('manage_wiki'):
        sections = WikiSection.query.order_by(WikiSection.sort_order).all()
    else:
        sections = (WikiSection.query.filter_by(is_published=True)
                    .order_by(WikiSection.sort_order).all())
    return render_template('wiki/_help_browse.html', sections=sections)


@wiki_bp.route('/wiki/help/<key>')
@login_required
def help_article(key):
    """The article claiming this key, or the gap plus a way to fill it."""
    if not is_registered(key):
        abort(404)

    article = WikiArticle.query.filter_by(help_key=key).first()
    if not article or (not article.is_published and not can('manage_wiki')):
        return render_template('wiki/_help_empty.html', key=key, label=label_for(key),
                               can_write=can('manage_wiki'))

    return render_template('wiki/_help_article.html', article=article,
                           blocks=load_blocks(article.sections_json))


@wiki_bp.route('/wiki/help/article/<int:article_id>')
@login_required
def help_article_by_id(article_id):
    """An article picked from the tray's browse list — same wrapper as the key path."""
    article = WikiArticle.query.get_or_404(article_id)
    if not article.is_published and not can('manage_wiki'):
        abort(403)
    return render_template('wiki/_help_article.html', article=article,
                           blocks=load_blocks(article.sections_json))


#------ Image upload & serve ------

@wiki_bp.route('/wiki/upload-image', methods=['POST'])
@login_required
@require('manage_wiki', real_user=True)
def upload_image():
    file = request.files.get('file')
    if not file:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    ext = file.filename.rsplit ('.', 1)[-1].lower() if '.' in file.filename else ''
    # No svg: it can carry script and is served from our own origin.
    if ext not in {'jpg', 'jpeg', 'png', 'gif', 'webp'}:
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


#------ Video upload & serve ------

_VIDEO_EXTENSIONS = {'mp4', 'webm'}
_VIDEO_MAX_BYTES = 200 * 1024 * 1024

@wiki_bp.route('/wiki/upload-video', methods=['POST'])
@login_required
@require('manage_wiki', real_user=True)
def upload_video():
    file = request.files.get('file')
    if not file:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in _VIDEO_EXTENSIONS:
        return jsonify({'success': False, 'error': 'File type not allowed'}), 400

    file_bytes = file.read()
    if len(file_bytes) > _VIDEO_MAX_BYTES:
        return jsonify({'success': False, 'error': f'Video is too large (max {_VIDEO_MAX_BYTES // (1024 * 1024)}MB).'}), 400

    filename = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = os.path.join(current_app.root_path, 'static', 'wiki-uploads', 'videos')
    os.makedirs(upload_dir, exist_ok=True)
    with open(os.path.join(upload_dir, filename), 'wb') as out:
        out.write(file_bytes)

    # Local file is already saved and servable — a NAS failure here must
    # never fail the upload, so back it up on a background thread.
    from app.modules.core.shared.services.nas import upload_app_file, _run_in_background
    _app_obj = current_app._get_current_object()

    def _backup_to_nas():
        try:
            upload_app_file(file_bytes, '/Admin/OVP/Wiki', filename)
        except RuntimeError as e:
            _app_obj.logger.error(f'Wiki video NAS backup failed for {filename}: {e}')

    _run_in_background(_app_obj, _backup_to_nas)

    return jsonify({
        'success': True,
        'filename': filename,
        'url': url_for('static', filename=f'wiki-uploads/videos/{filename}')
    })

def _int_or_none(value):
    """Form ids arrive as text. Blank means 'not given'; anything else non-numeric is a bad request."""
    value = (value or '').strip()
    if not value:
        return None
    if not value.isdigit():
        abort(400)
    return int(value)


def _next_sort_order(model, **filters):
    """One past the current highest, so new rows land at the end of their list."""
    query = model.query
    if filters:
        query = query.filter_by(**filters)
    highest = query.order_by(model.sort_order.desc()).first()
    return (highest.sort_order or 0) + 1 if highest else 0


def _unique_section_slug(title):
    """Section slugs are unique in the database, so a clash gets a suffix."""
    base = slugify(title) or 'section'
    slug, suffix = base, 2
    while WikiSection.query.filter_by(slug=slug).first():
        slug = f'{base}-{suffix}'
        suffix += 1
    return slug


def _claim_help_key(article, key):
    """One article per key, so a "?" can never be ambiguous. Returns the titles it cleared."""
    key = (key or '').strip()
    if key and not is_registered(key):
        key = ''

    cleared = []
    if key:
        others = WikiArticle.query.filter(WikiArticle.help_key == key,
                                          WikiArticle.id != article.id).all()
        cleared = [other.title for other in others]
        if cleared:
            db.session.execute(
                update(WikiArticle)
                .where(WikiArticle.help_key == key, WikiArticle.id != article.id)
                # Assigning updated_at to itself is what stops onupdate firing.
                .values(help_key=None, updated_at=WikiArticle.updated_at)
                .execution_options(synchronize_session=False)
            )

    article.help_key = key or None
    return cleared


def _apply_order(model, ids, extra=None):
    """Write sort_order from list position, leaving updated_at untouched."""
    for position, row_id in enumerate(ids):
        row_id = _int_or_none(str(row_id))
        if row_id is None:
            continue
        values = {'sort_order': position}
        if extra:
            values.update(extra)
        if hasattr(model, 'updated_at'):
            # Assigning the column to itself is what stops onupdate firing.
            values['updated_at'] = model.updated_at
        db.session.execute(update(model).where(model.id == row_id).values(**values))
    db.session.commit()


def _editor_context(article, section):
    """Everything the article editor page needs, for both new and existing articles."""
    content = (article.draft_sections_json or article.sections_json or '') if article else ''
    return {
        'article': article,
        'section': section,
        'content_json': content,
        'draft_restored': bool(article and article.draft_sections_json),
        'help_key_groups': HELP_KEY_GROUPS,
    }


# ------ Editor Sections ------
@wiki_bp.route('/wiki/editor')
@login_required
@require('manage_wiki', real_user=True)
def editor_dashboard():
    sections = WikiSection.query.order_by(WikiSection.sort_order).all()
    claimed = [row.help_key for row in WikiArticle.query.with_entities(WikiArticle.help_key).all()]
    return render_template('wiki/editor_dashboard.html', sections=sections,
                           templates=picker_options(),
                           help_key_groups=HELP_KEY_GROUPS,
                           coverage=coverage(claimed))

@wiki_bp.route('/wiki/editor/sections/reorder', methods=['POST'])
@login_required
@require('manage_wiki', real_user=True)
def reorder_sections():
    _apply_order(WikiSection, (request.get_json(silent=True) or {}).get('section_ids') or [])
    return jsonify({'success': True})


@wiki_bp.route('/wiki/editor/articles/reorder', methods=['POST'])
@login_required
@require('manage_wiki', real_user=True)
def reorder_articles():
    """The list a row is dropped into owns it, so the move and the order are one write."""
    payload = request.get_json(silent=True) or {}
    section_id = _int_or_none(str(payload.get('section_id') or ''))
    extra = {'section_id': WikiSection.query.get_or_404(section_id).id} if section_id else None
    _apply_order(WikiArticle, payload.get('article_ids') or [], extra)
    return jsonify({'success': True})


@wiki_bp.route('/wiki/editor/article/create', methods=['POST'])
@login_required
@require('manage_wiki', real_user=True)
def create_article():
    """From the new-article overlay: seed the chosen skeleton, then open the editor."""
    section_id = _int_or_none(request.form.get('section_id'))
    title      = request.form.get('title', '').strip()
    template   = request.form.get('template', 'blank').strip()
    help_key   = request.form.get('help_key', '').strip()

    if not title or not section_id:
        return redirect(url_for('wiki.editor_dashboard'))

    section = WikiSection.query.get_or_404(section_id)
    article = WikiArticle(
        section_id=section.id,
        title=title,
        slug=slugify(title),
        sections_json=json.dumps(template_document(template)),
        sort_order=_next_sort_order(WikiArticle, section_id=section.id),
        is_published=False
    )
    db.session.add(article)
    db.session.flush()
    _claim_help_key(article, help_key)
    db.session.commit()

    return redirect(url_for('wiki.edit_article', article_id=article.id))


@wiki_bp.route('/wiki/editor/article/<int:article_id>/edit')
@login_required
@require('manage_wiki', real_user=True)
def edit_article(article_id):
    article = WikiArticle.query.get_or_404(article_id)
    return render_template('wiki/editor_article.html', **_editor_context(article, article.section))


@wiki_bp.route('/wiki/editor/article/save', methods=['POST'])
@login_required
@require('manage_wiki', real_user=True)
def save_article():
    article_id    = _int_or_none(request.form.get('article_id'))
    section_id    = _int_or_none(request.form.get('section_id'))
    title         = request.form.get('title', '').strip()
    sections_json = request.form.get('sections_json', '[]')
    is_published  = request.form.get('is_published') == 'on'
    help_key      = request.form.get('help_key', '').strip()

    if not title or not section_id:
        return jsonify({'success': False, 'error': 'Title and section are required'}), 400

    try:
        payload = json.loads(sections_json)
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid content data'}), 400

    document = sanitize_document(payload)
    if document is None:
        return jsonify({'success': False, 'error': 'Invalid content data'}), 400

    sections_json = json.dumps(document)

    if article_id:
        article               = WikiArticle.query.get_or_404(article_id)
        article.section_id    = section_id
        article.title         = title
        article.slug          = article.slug or slugify(title)
        article.sections_json = sections_json
        article.is_published  = is_published
        article.updated_at    = datetime.utcnow()
    else:
        article = WikiArticle(section_id=section_id, title=title,
                              slug=slugify(title), sections_json=sections_json,
                              sort_order=_next_sort_order(WikiArticle, section_id=section_id),
                              is_published=is_published)
        db.session.add(article)

    # Saving is what makes the draft live, so the stored draft is spent.
    article.draft_sections_json = None
    article.draft_saved_at      = None

    db.session.flush()
    cleared = _claim_help_key(article, help_key)

    db.session.commit()
    if cleared:
        flash("Help key moved from '%s'" % "', '".join(cleared), 'info')
    return redirect(url_for('wiki.edit_article', article_id=article.id))


@wiki_bp.route('/wiki/editor/article/autosave', methods=['POST'])
@login_required
@require('manage_wiki', real_user=True)
def autosave_article():
    """Park the working copy in draft_sections_json. Save is what makes it live."""
    article_id    = _int_or_none(request.form.get('article_id'))
    section_id    = _int_or_none(request.form.get('section_id'))
    title         = request.form.get('title', '').strip()
    sections_json = request.form.get('sections_json', '')

    try:
        payload = json.loads(sections_json)
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid content data'}), 400

    document = sanitize_document(payload)
    if document is None:
        return jsonify({'success': False, 'error': 'Invalid content data'}), 400

    if article_id:
        article = WikiArticle.query.get_or_404(article_id)
    elif title and section_id and document['blocks']:
        article = WikiArticle(section_id=section_id, title=title,
                              slug=slugify(title),
                              sections_json=json.dumps(empty_document()),
                              sort_order=_next_sort_order(WikiArticle, section_id=section_id),
                              is_published=False)
        db.session.add(article)
        db.session.commit()
    else:
        # A new article with no title or no content yet — nothing worth keeping.
        return jsonify({'success': False, 'error': 'Nothing to save yet'})

    saved_at = datetime.utcnow()
    db.session.execute(
        update(WikiArticle)
        .where(WikiArticle.id == article.id)
        # Assigning updated_at to itself is what stops onupdate firing — readers see that date.
        .values(draft_sections_json=json.dumps(document), draft_saved_at=saved_at,
                updated_at=WikiArticle.updated_at)
    )
    db.session.commit()

    return jsonify({'success': True, 'article_id': article.id})


@wiki_bp.route('/wiki/editor/article/<int:article_id>/toggle-publish', methods=['POST'])
@login_required
@require('manage_wiki', real_user=True)
def toggle_article_publish(article_id):
    article = WikiArticle.query.get_or_404(article_id)
    article.is_published = not article.is_published
    db.session.commit()
    return jsonify({'success': True, 'is_published': article.is_published})


@wiki_bp.route('/wiki/editor/article/<int:article_id>/delete', methods=['POST'])
@login_required
@require('manage_wiki', real_user=True)
def delete_article(article_id):
    article = WikiArticle.query.get_or_404(article_id)
    db.session.delete(article)
    db.session.commit()
    return jsonify({'success': True})



@wiki_bp.route('/wiki/editor/section/save', methods=['POST'])
@login_required
@require('manage_wiki', real_user=True)
def save_section():
    section_id     = request.form.get('section_id', '').strip()
    title          = request.form.get('title', '').strip()
    relevant_roles = ','.join(request.form.getlist('relevant_roles'))
    is_published   = request.form.get('is_published') == 'on'

    if not title:
        return redirect(url_for('wiki.editor_dashboard'))

    if section_id:
        section                = WikiSection.query.get_or_404(_int_or_none(section_id))
        section.title          = title
        section.relevant_roles = relevant_roles or None
        section.is_published   = is_published
    else:
        section = WikiSection(
            title=title, slug=_unique_section_slug(title),
            relevant_roles=relevant_roles or None,
            sort_order=_next_sort_order(WikiSection),
            is_published=is_published
        )
        db.session.add(section)

    db.session.commit()
    return redirect(url_for('wiki.editor_dashboard'))


@wiki_bp.route('/wiki/editor/section/<int:section_id>/toggle-publish', methods=['POST'])
@login_required
@require('manage_wiki', real_user=True)
def toggle_section_publish(section_id):
    section = WikiSection.query.get_or_404(section_id)
    section.is_published = not section.is_published
    db.session.commit()
    return jsonify({'success': True, 'is_published': section.is_published})


@wiki_bp.route('/wiki/editor/section/<int:section_id>/delete', methods=['POST'])
@login_required
@require('manage_wiki', real_user=True)
def delete_section(section_id):
    section = WikiSection.query.get_or_404(section_id)
    db.session.delete(section)
    db.session.commit()
    return jsonify({'success': True})