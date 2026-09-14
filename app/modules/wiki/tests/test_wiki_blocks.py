"""Conversion, sanitising and rendering of wiki article content."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from app.modules.wiki.lib.blocks import (
    clean_html, is_editorjs, load_blocks, to_editorjs,
)


def _render(app, old_blocks):
    """Convert an old block array and render it through the article partial."""
    blocks = load_blocks(json.dumps(to_editorjs(old_blocks)))
    article = SimpleNamespace(title='T', updated_at=datetime.now(timezone.utc))
    template = app.jinja_env.get_template('wiki/_article_content.html')
    return template.render(article=article, blocks=blocks)


# ------ One test per old block type ------

def test_body_keeps_text_and_line_breaks(app):
    html = _render(app, [{'type': 'body', 'content': 'One\nTwo'}])
    assert '<p class="wiki-block-body">One<br>Two</p>' in html


def test_body_escapes_markup(app):
    html = _render(app, [{'type': 'body', 'content': '<b>x</b>'}])
    assert '&lt;b&gt;x&lt;/b&gt;' in html


def test_h3_renders_as_heading(app):
    html = _render(app, [{'type': 'h3', 'content': 'A heading'}])
    assert '<h3 class="wiki-block-h3">A heading</h3>' in html


def test_richtext_splits_into_paragraphs_and_lists(app):
    old = [{'type': 'richtext', 'content': '<p>Hi <strong>you</strong></p><ul><li>a</li><li>b</li></ul>'}]
    html = _render(app, old)
    assert '<p class="wiki-block-body">Hi <strong>you</strong></p>' in html
    assert '<li>a</li>' in html and '<li>b</li>' in html


def test_callout_variants(app):
    html = _render(app, [
        {'type': 'callout', 'content': 'Plain'},
        {'type': 'callout-pine', 'content': 'Pine'},
    ])
    assert '<div class="wiki-block-callout">Plain</div>' in html
    assert 'wiki-block-callout--pine' in html


def test_list_keeps_items(app):
    html = _render(app, [{'type': 'list', 'items': ['alpha', 'beta']}])
    assert '<ul class="wiki-block-list">' in html
    assert '<li>alpha</li>' in html and '<li>beta</li>' in html


def test_image_keeps_url_and_caption(app):
    html = _render(app, [{'type': 'image', 'url': '/static/x.png', 'caption': 'Cap'}])
    assert 'src="/static/x.png"' in html
    assert '<figcaption>Cap</figcaption>' in html


def test_video_upload_renders_video_tag(app):
    html = _render(app, [{'type': 'video', 'source': 'upload', 'url': '/static/y.mp4'}])
    assert '<video' in html and '<iframe' not in html


def test_video_embed_renders_iframe(app):
    html = _render(app, [{'type': 'video', 'content': 'https://www.youtube.com/watch?v=abc123'}])
    assert 'https://www.youtube.com/embed/abc123' in html
    assert '<video' not in html


# ------ Conversion behaviour ------

def test_conversion_is_idempotent():
    document = to_editorjs([{'type': 'body', 'content': 'Hello'}])
    assert is_editorjs(document)
    assert load_blocks(json.dumps(document)) == load_blocks(json.dumps(document))


def test_old_array_still_renders_before_migration(app):
    blocks = load_blocks(json.dumps([{'type': 'body', 'content': 'Hello'}]))
    assert blocks[0]['type'] == 'paragraph'


def test_unknown_block_type_is_dropped():
    document = to_editorjs([{'type': 'mystery', 'content': 'x'}])
    assert document['blocks'] == []


# ------ Sanitising ------

def test_clean_html_keeps_inline_formatting():
    assert clean_html('<b>bold</b> <em>em</em>') == '<b>bold</b> <em>em</em>'


def test_clean_html_strips_scripts_and_handlers():
    cleaned = clean_html('<script>alert(1)</script><b onclick="x()">hi</b>')
    assert 'script' not in cleaned
    assert 'onclick' not in cleaned
    assert 'hi' in cleaned


def test_clean_html_strips_javascript_links():
    assert 'javascript' not in clean_html('<a href="javascript:alert(1)">x</a>')
