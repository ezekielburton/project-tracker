"""
Wiki article content: the Editor.js document shape, conversion from the old
block array, and the inline-HTML allowlist applied on save.
"""

import html
import json
import re
import uuid
from html.parser import HTMLParser

import nh3

EDITORJS_VERSION = '2.30.7'

# Inline formatting Editor.js emits inside paragraph/header text.
ALLOWED_TAGS = {'b', 'strong', 'i', 'em', 'u', 's', 'a', 'code', 'mark', 'br'}
ALLOWED_ATTRIBUTES = {'a': {'href', 'title'}}
ALLOWED_URL_SCHEMES = {'http', 'https', 'mailto'}

_BLOCK_TAGS = {'p', 'div', 'blockquote', 'pre'}
_HEADER_TAGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
_LIST_TAGS = {'ul', 'ol'}


def clean_html(value):
    """Strip everything outside the inline allowlist from editor text."""
    if not value:
        return ''
    return nh3.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
    )


def _has_content(text):
    """True when text holds something other than line breaks and whitespace."""
    return bool(re.sub(r'<br\s*/?>', '', text or '').strip())


def _block_id():
    return uuid.uuid4().hex[:10]


def _block(block_type, data):
    return {'id': _block_id(), 'type': block_type, 'data': data}


def empty_document():
    """An Editor.js document with no blocks."""
    return {'time': 0, 'blocks': [], 'version': EDITORJS_VERSION}


def is_editorjs(value):
    """True when the parsed content is an Editor.js document rather than the old array."""
    return isinstance(value, dict) and isinstance(value.get('blocks'), list)


# ------ Old rich text -> Editor.js blocks ------

class _RichTextSplitter(HTMLParser):
    """Splits stored rich-text HTML into paragraph, header and list blocks."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self._buf = []
        self._mode = None
        self._level = 3
        self._list_style = 'unordered'
        self._items = []
        self._in_list = False
        self._in_item = False

    # -- buffer helpers --

    def _text(self):
        return ''.join(self._buf).strip()

    def _flush(self):
        text = self._text()
        self._buf = []
        if not _has_content(text):
            self._mode = None
            return
        if self._mode == 'header':
            self.blocks.append(_block('header', {'text': clean_html(text), 'level': self._level}))
        else:
            self.blocks.append(_block('paragraph', {'text': clean_html(text)}))
        self._mode = None

    def _flush_list(self):
        items = [clean_html(i) for i in self._items if _has_content(i)]
        self._items = []
        self._in_list = False
        self._in_item = False
        if items:
            self.blocks.append(_block('list', {'style': self._list_style, 'items': items}))

    def _append(self, chunk):
        if self._in_item:
            self._items[-1] += chunk
        elif not self._in_list:
            self._buf.append(chunk)

    # -- parser hooks --

    def handle_starttag(self, tag, attrs):
        if tag in _LIST_TAGS:
            self._flush()
            self._in_list = True
            self._list_style = 'ordered' if tag == 'ol' else 'unordered'
            return
        if tag == 'li':
            self._in_item = True
            self._items.append('')
            return
        if tag in _HEADER_TAGS:
            self._flush()
            self._mode = 'header'
            self._level = 3
            return
        if tag in _BLOCK_TAGS:
            self._flush()
            self._mode = 'paragraph'
            return
        if tag == 'br':
            self._append('<br>')
            return
        if tag in ALLOWED_TAGS:
            self._append(self.get_starttag_text() or f'<{tag}>')

    def handle_startendtag(self, tag, attrs):
        if tag == 'br':
            self._append('<br>')

    def handle_endtag(self, tag):
        if tag in _LIST_TAGS:
            self._flush_list()
            return
        if tag == 'li':
            self._in_item = False
            return
        if tag in _HEADER_TAGS or tag in _BLOCK_TAGS:
            self._flush()
            return
        if tag in ALLOWED_TAGS and tag != 'br':
            self._append(f'</{tag}>')

    def handle_data(self, data):
        if not data.strip() and not self._buf and not self._in_item:
            return
        self._append(html.escape(data, quote=False))

    def close(self):
        super().close()
        if self._in_list:
            self._flush_list()
        self._flush()


def richtext_to_blocks(value):
    """Convert one stored rich-text block's HTML into Editor.js blocks."""
    if not value or not value.strip():
        return []
    parser = _RichTextSplitter()
    parser.feed(value)
    parser.close()
    return parser.blocks


# ------ Old block array -> Editor.js document ------

def _plain_to_text(value):
    """Escape plain-text content and keep its line breaks."""
    return html.escape(value or '', quote=False).replace('\r\n', '\n').replace('\n', '<br>')


def _convert_one(block):
    """Convert one old block. Returns a list, since rich text can split into several."""
    kind = (block or {}).get('type')

    if kind == 'body':
        text = _plain_to_text(block.get('content'))
        return [_block('paragraph', {'text': text})] if text else []

    if kind == 'richtext':
        return richtext_to_blocks(block.get('content'))

    if kind == 'h3':
        text = _plain_to_text(block.get('content'))
        return [_block('header', {'text': text, 'level': 3})] if text else []

    if kind in ('callout', 'callout-pine'):
        text = _plain_to_text(block.get('content'))
        variant = 'pine' if kind == 'callout-pine' else 'default'
        return [_block('helixCallout', {'text': text, 'variant': variant})] if text else []

    if kind == 'list':
        items = [_plain_to_text(i) for i in (block.get('items') or []) if (i or '').strip()]
        return [_block('list', {'style': 'unordered', 'items': items})] if items else []

    if kind == 'image':
        url = block.get('url')
        if not url:
            return []
        return [_block('image', {
            'file': {'url': url},
            'caption': _plain_to_text(block.get('caption')),
            'withBorder': False,
            'withBackground': False,
            'stretched': False,
        })]

    if kind == 'video':
        source = 'upload' if block.get('source') == 'upload' else 'embed'
        url = block.get('url') if source == 'upload' else block.get('content')
        if not url:
            return []
        return [_block('helixVideo', {'source': source, 'url': url})]

    return []


def to_editorjs(legacy_blocks):
    """Convert the old block array into an Editor.js document."""
    blocks = []
    for old in legacy_blocks or []:
        blocks.extend(_convert_one(old))
    return {'time': 0, 'blocks': blocks, 'version': EDITORJS_VERSION}


# ------ Reading for the renderer ------

def _normalise_list_items(items):
    """List items are stored as plain strings; tolerate the nested object shape."""
    out = []
    for item in items or []:
        if isinstance(item, dict):
            out.append(item.get('content', ''))
        else:
            out.append(item)
    return out


def load_blocks(sections_json):
    """Parse stored article content into the block list the renderer walks."""
    try:
        parsed = json.loads(sections_json or '[]')
    except ValueError:
        return []

    if not is_editorjs(parsed):
        # Content still in the old array shape renders until the legacy column is dropped.
        parsed = to_editorjs(parsed if isinstance(parsed, list) else [])

    blocks = []
    for block in parsed.get('blocks') or []:
        if not isinstance(block, dict):
            continue
        data = dict(block.get('data') or {})
        if block.get('type') == 'list':
            data['items'] = _normalise_list_items(data.get('items'))
        blocks.append({'type': block.get('type'), 'data': data})
    return blocks


# ------ Cleaning what the editor saves ------

def _safe_url(value, allow_remote=False):
    """Keep site-relative paths, plus http(s) URLs where remote is allowed."""
    url = (value or '').strip()
    if not url or url.startswith('//'):
        return ''
    if url.startswith('/'):
        return url
    if allow_remote and url.lower().startswith(('http://', 'https://')):
        return url
    return ''


def _clean_block(kind, data):
    """Clean one block's data. Returns None for empty or unrecognised blocks."""
    if kind == 'paragraph':
        text = clean_html(data.get('text'))
        return {'text': text} if _has_content(text) else None

    if kind == 'header':
        text = clean_html(data.get('text'))
        return {'text': text, 'level': 3} if _has_content(text) else None

    if kind == 'helixCallout':
        text = clean_html(data.get('text'))
        variant = 'pine' if data.get('variant') == 'pine' else 'default'
        return {'text': text, 'variant': variant} if _has_content(text) else None

    if kind == 'list':
        items = [clean_html(i) for i in _normalise_list_items(data.get('items'))]
        items = [i for i in items if _has_content(i)]
        style = 'ordered' if data.get('style') == 'ordered' else 'unordered'
        return {'style': style, 'items': items} if items else None

    if kind == 'image':
        url = _safe_url((data.get('file') or {}).get('url'))
        if not url:
            return None
        return {
            'file': {'url': url},
            'caption': clean_html(data.get('caption')),
            'withBorder': False,
            'withBackground': False,
            'stretched': False,
        }

    if kind == 'helixVideo':
        source = 'upload' if data.get('source') == 'upload' else 'embed'
        url = _safe_url(data.get('url'), allow_remote=(source == 'embed'))
        return {'source': source, 'url': url} if url else None

    return None


def sanitize_document(value):
    """Clean an Editor.js document for storage. Returns None if it is not one."""
    if not is_editorjs(value):
        return None

    blocks = []
    for block in value.get('blocks') or []:
        if not isinstance(block, dict):
            continue
        kind = block.get('type')
        data = _clean_block(kind, block.get('data') or {})
        if data is not None:
            blocks.append({'id': block.get('id') or _block_id(), 'type': kind, 'data': data})

    return {'time': value.get('time') or 0, 'blocks': blocks, 'version': EDITORJS_VERSION}
