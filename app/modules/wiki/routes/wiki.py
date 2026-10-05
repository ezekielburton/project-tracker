import json, uuid, os
from datetime import datetime
from flask import (Blueprint, render_template, request, jsonify, abort, redirect, url_for, current_app, flash)
from flask_login import current_user, login_required
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import WikiSection, WikiArticle, WikiSearchMiss
from app.modules.core.shared.lib.capabilities import can, effective_user, require
from app.modules.core.shared.lib.utils import slugify
from sqlalchemy import update
from app.modules.wiki.lib.blocks import (
    document_text, first_video_length, format_length, lead_with_video, load_blocks, sanitize_document,
)
from app.modules.wiki.lib.search import search_articles, searchable_count
from app.modules.wiki.lib.search_misses import (
    NOTE_MAX, asked_counts, dismiss, phrase_key, record_miss, write_next,
)
from app.modules.wiki.lib.freshness import review_label, reviewed_this_quarter
from app.modules.wiki.lib.relevance import dimmed_sections, order_hits, reader_scope, roles_text, scope_param
from app.modules.wiki.lib.reader import (
    most_read_articles, readable_sections, rail_items, recently_updated, related_articles, start_here,
)
from app.modules.wiki.lib.views import read_count, record_view
from app.modules.wiki.lib.votes import cast_vote, current_vote, not_useful
from app.modules.wiki.lib.uploads import delete_unused, unused_uploads, upload_root
from app.modules.wiki.lib.article_templates import picker_options, template_document
from app.modules.wiki.lib.help_keys import HELP_KEY_GROUPS, coverage, is_registered, label_for

wiki_bp = Blueprint('wiki', __name__, template_folder='../templates')


@wiki_bp.app_template_filter('wiki_review_label')
def _review_label_filter(reviewed_at):
    return review_label(reviewed_at)


@wiki_bp.app_template_filter('wiki_review_due')
def _review_due_filter(reviewed_at):
    return not reviewed_this_quarter(reviewed_at)


@wiki_bp.app_template_filter('wiki_section_roles')
def _section_roles_filter(section):
    return roles_text(section)


@wiki_bp.app_template_filter('wiki_duration')
def _duration_filter(seconds):
    return format_length(seconds)


@wiki_bp.app_template_filter('wiki_video_length')
def _video_length_filter(article):
    return first_video_length(article.sections_json)

# ------ Viewer ------

def _count_read(article, source):
    """Readers' visits count. People who manage the wiki don't, even while emulating."""
    if not can('manage_wiki', current_user):
        record_view(article.id, current_user.id, source)


def _reader_context(active, active_sub=None, current_section_id=None,
                    scope_endpoint='wiki.index', scope_args=None):
    """What every reader page needs: the reader's role and scope, and the rail."""
    role = effective_user().role
    scope = reader_scope(request.args.get('scope'))
    sections = readable_sections(include_drafts=can('manage_wiki'))
    context = {
        'role': role,
        'scope': scope,
        'scope_param': scope_param(scope),
        'rail': rail_items(sections, role, scope, current_section_id, link_scope=scope_param(scope)),
        'rail_active': active,
        'rail_active_sub': active_sub,
        'scope_endpoint': scope_endpoint,
        'scope_args': scope_args or {},
    }
    return context, sections


@wiki_bp.route('/wiki')
@login_required
def index():
    """The reader's home, on the rail: search, Start here, and what changed lately."""
    context, sections = _reader_context('home')
    return render_template('wiki/index.html', start=start_here(sections, context['role']),
                           recent=recently_updated(sections),
                           popular=most_read_articles(sections), **context)


@wiki_bp.route('/wiki/article/<int:article_id>')
@login_required
def get_article(article_id):
    """One article as its own page, on the rail."""
    article = WikiArticle.query.get_or_404(article_id)
    if not article.is_published and not can('manage_wiki'):
        abort(403)
    _count_read(article, 'page')
    context, sections = _reader_context(f'section-{article.section_id}', f'article-{article.id}',
                                        current_section_id=article.section_id,
                                        scope_endpoint='wiki.get_article',
                                        scope_args={'article_id': article.id})
    return render_template('wiki/article.html', article=article,
                           blocks=lead_with_video(load_blocks(article.sections_json)),
                           related=related_articles(sections, article),
                           reads=read_count(article.id),
                           can_vote=not can('manage_wiki', current_user),
                           vote=current_vote(article.id, current_user.id), **context)


@wiki_bp.route('/wiki/article/<int:article_id>/vote', methods=['POST'])
@login_required
def vote_article(article_id):
    """A reader's "Useful?" answer, always their own. Wiki managers don't vote."""
    article = WikiArticle.query.get_or_404(article_id)
    if not article.is_published or can('manage_wiki', current_user):
        abort(403)
    answer = request.form.get('helpful')
    if answer in ('yes', 'no'):
        cast_vote(article.id, current_user.id, answer == 'yes', request.form.get('note', ''))
    return redirect(url_for('wiki.get_article', article_id=article.id, _anchor='wiki-useful'))


@wiki_bp.route('/wiki/search')
@login_required
def search():
    """Search results for ?q=. A search that finds nothing is recorded for Write next."""
    query = request.args.get('q', '').strip()[:200]
    include_drafts = can('manage_wiki')
    context, _ = _reader_context('search', scope_endpoint='wiki.search',
                                 scope_args={'q': query} if query else {})
    role, scope = context['role'], context['scope']
    hits = order_hits(search_articles(query, include_drafts=include_drafts) if query else [],
                      role, scope)

    miss = asked = searched = None
    if query and not hits:
        searched = searchable_count(include_drafts=include_drafts)
        key = phrase_key(query)
        if key:
            # Authors' own misses are not reader demand. The real user decides, so emulating is skipped too.
            if not can('manage_wiki', current_user):
                miss = record_miss(query, key, current_user.id)
            asked = asked_counts(key)

    return render_template('wiki/search.html', query=query, hits=hits,
                           miss=miss, asked=asked, searched=searched,
                           dimmed=dimmed_sections([hit.section for hit in hits], role, scope),
                           **context)


@wiki_bp.route('/wiki/search/miss/<int:miss_id>/note', methods=['POST'])
@login_required
def note_search_miss(miss_id):
    """Attach what the person was trying to do to their own unanswered search."""
    miss = WikiSearchMiss.query.get_or_404(miss_id)
    if miss.user_id != current_user.id:
        abort(404)
    note = request.form.get('note', '').strip()[:NOTE_MAX]
    if note:
        miss.note = note
        db.session.commit()
    return redirect(url_for('wiki.search', q=miss.phrase))

# ------ Contextual help (the "?" tray) ------

@wiki_bp.route('/wiki/help')
@login_required
def help_browse():
    """The tray's browse list: the Help pill opened with no key."""
    if can('manage_wiki'):
        sections = WikiSection.query.order_by(WikiSection.sort_order).all()
    else:
        sections = (WikiSection.query.filter_by(is_published=True)
                    .order_by(WikiSection.sort_order).all())
    return render_template('wiki/_help_browse.html', sections=sections)


@wiki_bp.route('/wiki/help/<key>')
@login_required
def help_article(key):
    """The article that claims this key, or an empty state with a write link for admins."""
    if not is_registered(key):
        abort(404)

    article = WikiArticle.query.filter_by(help_key=key).first()
    if not article or (not article.is_published and not can('manage_wiki')):
        return render_template('wiki/_help_empty.html', key=key, label=label_for(key),
                               can_write=can('manage_wiki'))

    _count_read(article, 'tray')
    return render_template('wiki/_help_article.html', article=article,
                           blocks=lead_with_video(load_blocks(article.sections_json)),
                           reads=read_count(article.id))


@wiki_bp.route('/wiki/help/article/<int:article_id>')
@login_required
def help_article_by_id(article_id):
    """An article picked from the tray's browse list, in the same wrapper as the key route."""
    article = WikiArticle.query.get_or_404(article_id)
    if not article.is_published and not can('manage_wiki'):
        abort(403)
    _count_read(article, 'tray')
    return render_template('wiki/_help_article.html', article=article,
                           blocks=lead_with_video(load_blocks(article.sections_json)),
                           reads=read_count(article.id))


# ------ Image upload ------

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
    upload_dir = upload_root()
    os.makedirs(upload_dir, exist_ok=True)
    file.save(os.path.join(upload_dir, filename))

    return jsonify({
        'success': True,
        'filename': filename,
        'url': url_for('static', filename=f'wiki-uploads/{filename}')
    })


# ------ Video upload ------

_VIDEO_EXTENSIONS = {'mp4', 'webm'}
_VIDEO_MAX_BYTES = 200 * 1024 * 1024
_VIDEO_FORM_SLACK = 64 * 1024

@wiki_bp.route('/wiki/upload-video', methods=['POST'])
@login_required
@require('manage_wiki', real_user=True)
def upload_video():
    too_large = jsonify({'success': False,
                         'error': f'Video is too large (max {_VIDEO_MAX_BYTES // (1024 * 1024)}MB).'}), 400

    # Refused before the body is parsed. The slack covers the multipart framing around the file.
    if (request.content_length or 0) > _VIDEO_MAX_BYTES + _VIDEO_FORM_SLACK:
        return too_large

    file = request.files.get('file')
    if not file:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in _VIDEO_EXTENSIONS:
        return jsonify({'success': False, 'error': 'File type not allowed'}), 400

    filename = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = os.path.join(upload_root(), 'videos')
    os.makedirs(upload_dir, exist_ok=True)
    path = os.path.join(upload_dir, filename)

    # Streamed with a running count, since Content-Length can be absent or wrong.
    written = 0
    with open(path, 'wb') as out:
        for chunk in iter(lambda: file.stream.read(1024 * 1024), b''):
            written += len(chunk)
            if written > _VIDEO_MAX_BYTES:
                break
            out.write(chunk)
    if written > _VIDEO_MAX_BYTES:
        os.remove(path)
        return too_large

    # The local copy is already servable; the NAS backup runs in the background
    # so a NAS failure never fails the upload.
    from app.modules.core.shared.services.nas import upload_app_file, _run_in_background
    _app_obj = current_app._get_current_object()

    def _backup_to_nas():
        try:
            with open(path, 'rb') as saved:
                upload_app_file(saved.read(), '/Admin/OVP/Wiki', filename)
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
    """Give the article this key and clear it from any other (one article per key).
    An unregistered key clears it. Returns the titles that lost the key."""
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
    """Template context for the article editor. Loads the unsaved draft if there is one."""
    return {
        'article': article,
        'section': section,
        'content_json': article.draft_sections_json or article.sections_json or '',
        'draft_restored': bool(article.draft_sections_json),
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
                           coverage=coverage(claimed),
                           write_next=write_next(),
                           not_useful=not_useful(),
                           unused=unused_uploads())

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
    """Save one list's order. Rows in it also move to its section, so a
    cross-section drop is one write."""
    payload = request.get_json(silent=True) or {}
    section_id = _int_or_none(str(payload.get('section_id') or ''))
    extra = {'section_id': WikiSection.query.get_or_404(section_id).id} if section_id else None
    _apply_order(WikiArticle, payload.get('article_ids') or [], extra)
    return jsonify({'success': True})


@wiki_bp.route('/wiki/editor/misses/dismiss', methods=['POST'])
@login_required
@require('manage_wiki', real_user=True)
def dismiss_search_miss():
    key = request.form.get('phrase_key', '').strip()
    if key:
        dismiss(key)
    return redirect(url_for('wiki.editor_dashboard'))


@wiki_bp.route('/wiki/editor/uploads/clean', methods=['POST'])
@login_required
@require('manage_wiki', real_user=True)
def clean_uploads():
    removed = delete_unused()
    if removed:
        flash(f"Deleted {removed} unused file{'' if removed == 1 else 's'}", 'info')
    return redirect(url_for('wiki.editor_dashboard'))


@wiki_bp.route('/wiki/editor/article/create', methods=['POST'])
@login_required
@require('manage_wiki', real_user=True)
def create_article():
    """New-article overlay: seed the chosen skeleton, then open the editor."""
    section_id = _int_or_none(request.form.get('section_id'))
    title      = request.form.get('title', '').strip()
    template   = request.form.get('template', 'blank').strip()
    help_key   = request.form.get('help_key', '').strip()

    if not title or not section_id:
        return redirect(url_for('wiki.editor_dashboard'))

    section = WikiSection.query.get_or_404(section_id)
    document = template_document(template)
    article = WikiArticle(
        section_id=section.id,
        title=title,
        slug=slugify(title),
        sections_json=json.dumps(document),
        search_text=document_text(document),
        created_by_id=current_user.id,
        updated_by_id=current_user.id,
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

    # Articles are created from the dashboard, so the editor always sends an id.
    if not article_id or not title or not section_id:
        return jsonify({'success': False, 'error': 'Article, title and section are required'}), 400

    try:
        payload = json.loads(sections_json)
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid content data'}), 400

    document = sanitize_document(payload)
    if document is None:
        return jsonify({'success': False, 'error': 'Invalid content data'}), 400

    article               = WikiArticle.query.get_or_404(article_id)
    article.section_id    = section_id
    article.title         = title
    article.slug          = article.slug or slugify(title)
    article.sections_json = json.dumps(document)
    article.search_text   = document_text(document)
    article.is_published  = is_published
    article.updated_at    = datetime.utcnow()
    article.updated_by_id = current_user.id
    article.reviewed_at   = article.updated_at

    # The draft is now live, so clear it.
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
    """Store the working copy in draft_sections_json. Only Save makes it live."""
    article_id    = _int_or_none(request.form.get('article_id'))
    sections_json = request.form.get('sections_json', '')

    if not article_id:
        return jsonify({'success': False, 'error': 'Nothing to save yet'})

    try:
        payload = json.loads(sections_json)
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid content data'}), 400

    document = sanitize_document(payload)
    if document is None:
        return jsonify({'success': False, 'error': 'Invalid content data'}), 400

    article = WikiArticle.query.get_or_404(article_id)

    saved_at = datetime.utcnow()
    db.session.execute(
        update(WikiArticle)
        .where(WikiArticle.id == article.id)
        # Assigning updated_at to itself stops onupdate firing; readers see that date.
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


@wiki_bp.route('/wiki/editor/article/<int:article_id>/reviewed', methods=['POST'])
@login_required
@require('manage_wiki', real_user=True)
def mark_reviewed(article_id):
    """Confirm an unchanged article is still right, leaving its Last updated date alone."""
    article = WikiArticle.query.get_or_404(article_id)
    db.session.execute(
        update(WikiArticle)
        .where(WikiArticle.id == article.id)
        # Assigning updated_at to itself stops onupdate firing.
        .values(reviewed_at=datetime.utcnow(), updated_at=WikiArticle.updated_at)
    )
    db.session.commit()
    return redirect(url_for('wiki.editor_dashboard'))


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